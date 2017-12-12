import boto3
from boto3.dynamodb.conditions import Key, Attr
from pan_vpn_generic import deactivateLicense, paGroupDelPaPeers

def room_for_rebalance(paGroupList, maxVpcPerPaGroup):
    """Retruns the FromPaGroup and ToPaGroup if there is a room for rebalance
    """
    # Find total number of VPCs
    num_of_paGroups = len(paGroupList)
    total_vpcs = 0
    for paGroup in paGroupList:
        total_vpcs += paGroup['VpcCount']

    optimal_number_of_paGroups = total_vpcs // maxVpcPerPaGroup
    if total_vpcs % maxVpcPerPaGroup:
        # Add one to support reminder VPCs
        optimal_number_of_paGroups += 1
    print("Totat VPCs: {0}".format(total_vpcs))
    print("Current number of PA Groups: {0}".format(num_of_paGroups))
    print("Optimal number of PA Groups: {0}".format(optimal_number_of_paGroups))

    if optimal_number_of_paGroups == num_of_paGroups:
        print("No room for optimization")
        return False
    else:
        # There is room for optimization. Identify PaGroup (fromPaGroup) from where a vpn can be moved to another PaGroup (toPaGroup)
        # First identify PA Groups which has room
        paGroupsWithCapcity = []
        highestVpcCount = 0
        lowestVpcCount = maxVpcPerPaGroup
        for paGroup in paGroupList:
            if paGroup['VpcCount'] < maxVpcPerPaGroup and paGroup['VpcCount'] != 0:
                paGroupsWithCapcity.append(paGroup)
                if paGroup['VpcCount'] > highestVpcCount: highestVpcCount = paGroup['VpcCount']
                if paGroup['VpcCount'] < lowestVpcCount: lowestVpcCount = paGroup['VpcCount']
        if len(paGroupsWithCapcity) <=1:
            print("No room for optimization after removing PaGroups with 0 and max VPC counts")
            return False
        if lowestVpcCount == highestVpcCount:
            # All PaGroup in paGroupsWithCapcity has same number of VPCs
            result = {}
            result['ToPaGroup'] = paGroupsWithCapcity[0]
            result['FromPaGroup'] = paGroupsWithCapcity[-1]
        else:
            paGroupsWithHighestVpcCount = [paGroup for paGroup in paGroupsWithCapcity if paGroup['VpcCount'] == highestVpcCount]
            paGroupsWithLowestVpcCount = [paGroup for paGroup in paGroupsWithCapcity if paGroup['VpcCount'] == lowestVpcCount]
            result = {}
            result['ToPaGroup'] = paGroupsWithHighestVpcCount[0]
            result['FromPaGroup'] = paGroupsWithLowestVpcCount[-1]
        return result

def deleteStack(awsRegion, stackName):
    """Deletes the PAGroup CFT stack
    """
    try:
        cft = boto3.client('cloudformation', region_name=awsRegion)
        cft.delete_stack(StackName=stackName)
        print("Successfully deleted the stack: {}".format(stackName))
    except Exception as e:
        print("Error from deleteStack(), Error: {}".format(str(e)))

def updateBgpTunnelIpPool(tableName, paGroupName, region):
    """Updates the Transit BgpTunnleIpPool with attribute "Available=YES" and VpcId and PaGroupName to Null
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name = region)
        table = dynamodb.Table(tableName)
        response = table.scan(FilterExpression=Attr('PaGroupName').eq(paGroupName))
        LastEvaluatedKey = True
        while LastEvaluatedKey:
            if 'LastEvaluatedKey' in response:
                response = table.scan(FilterExpression=Attr('PaGroupName').eq(paGroupName))
            else:
                LastEvaluatedKey = False
        if response['Items']:
            table.update_item(Key={'IpSegment':response['Items'][0]['IpSegment']},AttributeUpdates={'Available':{'Value':'YES','Action':'PUT'}, 'VpcId':{'Value':'Null','Action':'PUT'}, 'PaGroupName':{'Value':'Null', 'Action': 'PUT'}})
            print("Successfully Updated BgpIpPoolTable attribute Available=YES and VpcId & PaGroupName to Null")
            return response['Items'][0]['VpcId']
    except Exception as e:
        print("Error from updateBgpTunnelIpPool, Error: {}".format(str(e)))

def updatePaGroupInfo(tableName, paGroup, region):
    """Updates the Transit PaGroupInfo table attribute with "InUse=NO" and "VpcCount=0"
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name = region)
        table = dynamodb.Table(tableName)
        item={
                'PaGroupName': paGroup['PaGroupName'],
                'N1Asn': str(paGroup['N1Asn']),
                'N2Asn': str(paGroup['N2Asn']),
                'InUse': 'NO',
                'VpcCount': 0
             }
        table.put_item(Item=item)
        print("Updated PaGroup: {} to its Initial Values".format(paGroup['PaGroupName']))
    except Exception as e:
        print("Error from updatePaGroupInfo, Error: {}".format(str(e)))
       
def updateTransitConfig(tableName, region):
    """Updates the Transit Config table attribute with RebalanceInProgress=False
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name = region)
        table = dynamodb.Table(tableName)
        table.put_item(Item={'Property':'RebalanceInProgress', 'Value':'False'})
        print("Updated RebalanceInProgress=False".format(tableName))
    except Exception as e:
        print("Error from updateTransitConfig, Error: {}".format(str(e)))


def decommisionUnusedPaGroup(api_key, paGroupList, transitConfig, dry_run=False):
    """Detect and decommision any unused PA Group
    """
    DeCommisionedPaGroups = []
    for paGroup in paGroupList:
        if paGroup['VpcCount'] == 0:
            DeCommisionedPaGroups.append(paGroup['PaGroupName'])
            if dry_run: continue # Incase of Dry run, don't do any de-configuration
            # Call function to deactivate license on each node
            deactivateLicense(paGroup['N1Mgmt'], api_key)
            deactivateLicense(paGroup['N2Mgmt'], api_key)
            # Call function to remove PA Peers
            paGroupDelPaPeers(api_key, paGroup, paGroupList)
            # Terminate PA Group stack
            deleteStack(paGroup['StackRegion'],paGroup['PaGroupName'] )
            # Once the stack is deleted you need to update the PaGroup item to its initial stage
            updatePaGroupInfo(transitConfig['TransitPaGroupInfo'], paGroup, transitConfig['Region'])
            # Code to truncate DynamoDB record related to PA Group
            updateBgpTunnelIpPool(transitConfig['TransitBgpTunnelIpPool'], paGroup['PaGroupName'], transitConfig['Region'])
            # Remove paGroup from paGroupList
            paGroupList.remove(paGroup)
    #Update Transit Config table RebalanceInProgress to False/Null
    #updateTransitConfig(transitConfig['TransitConfig'], transitConfig['Region'])
    return DeCommisionedPaGroups

def rebalance(api_key, paGroupList, maxVpcPerPaGroup, transitConfig, keep_unused_paGroups=False):
    """Skeleton Lambda function which takes care of Rebalance operation
    """
    result = room_for_rebalance(paGroupList, maxVpcPerPaGroup)
    if not result:
        # Check if there is any PA Group that should be decommisioned
        DeCommisionedPaGroups = decommisionUnusedPaGroup(api_key, paGroupList, transitConfig, dry_run=keep_unused_paGroups)
        updateTransitConfig(transitConfig['TransitConfig'], transitConfig['Region'])
        if len(DeCommisionedPaGroups) == 0:
            print("All PA Groups are in use")
        else:
            print("Following PA Groups are decommisioned:")
            print("NOTE: dry_run = {0}".format(keep_unused_paGroups))
            for pa in DeCommisionedPaGroups:
                print("DeCommisioned PaGroup: {}".format(pa))
        return False # No rebalance pending
    else:
        # Result is of format {"from":<paGroup>, "to":<paGroup> }
        return result
