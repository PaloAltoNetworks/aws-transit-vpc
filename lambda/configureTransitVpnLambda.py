import boto3
from boto3.dynamodb.conditions import Key, Attr
import logging, os
from commonLambdaFunctions import publishToSns, fetchFromTransitConfigTable
import pan_vpn_generic

logger = logging.getLogger()
logger.setLevel(logging.INFO)

'''
Input:
{
    'Action': 'ConfigureTransitVpn',
    'PaGroupName': event['PaGroupName'],
    'IpSegment': event['IpSegment'],
    'VpnN1': vpnId1,
    'VpnN2': vpnId2,
    'VpcId': event['VpcId'],
    'Region': event['Region'],
    'TransitVpnBucketName': event['TransitVpnBucketName'],
    'SubscriberSnsArn': subscriberConfig['SubscriberSnsArn'],
    'SubscriberAssumeRoleArn': subscriberConfig['SubscriberAssumeRoleArn']
}

'''
#region = 'us-east-1'
transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

dynamodb = boto3.resource('dynamodb', region_name=region)


#transitConfigTable="TransitConfig"

def updateVpcTable(tableName,data,status):
    """Updates the Transit VpcTable with VpcId, Node1VpnId, Node2VpnId, Region, IpSegment and CurrentStatus
    """
    try:
        #VpcId is the primary key for VpcTable
        table=dynamodb.Table(tableName)
        response=table.update_item(Key={'VpcId':data['VpcId']},AttributeUpdates={'CurrentStatus':{'Value':status,'Action':'PUT'},'Node1VpnId':{'Value':data['VpnN1'],'Action':'PUT'},'Node2VpnId':{'Value':data['VpnN2'],'Action':'PUT'}, 'Region':{'Value':data['Region'],'Action':'PUT'}, 'IpSegment':{'Value':data['IpSegment'],'Action':'PUT'}})
    except Exception as e:
        logger.error("Updating Transit VpcTalbe is Failed, Error: {}".format(str(e)))
def updateBgpTunnelIpPool(bgpTableName,ipSegment):
    """updates Transit BgpTunnleIpPool table attribute 'Available=YES'
    """
    try:
        table=dynamodb.Table(bgpTableName)
        #Update BgpTunnelIpPool table Attribute "Available"="YES"
        tableConn.update_item(Key={'IpSegment':ipSegment},AttributeUpdates={'Available':{'Value':'YES','Action':'PUT'}})
        logger.info("Successfully Updated BgpTunnleIpPool Table attribute Available=YES")
    except Exception as e:
        logger.error("Update BgpTunnelIpPool is failed, Error: {}".format(str(e)))
        
def updatePaGroup(paGroupTableName,paGroupName,value):
    """Updates Transit PaGroupInfo table attribute VpcCount to either +1 or -1 based on the value paramater passed to the function
    """
    try:
        table=dynamodb.Table(paGroupTableName)
        response = table.query(KeyConditionExpression=Key('PaGroupName').eq(paGroupName))['Items']
        if response:
            if response[0]['VpcCount']>0:
                table.update_item(Key={'PaGroupName':paGroupName},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'},'VpcCount':{'Value':value,'Action':'ADD'}})
                logger.info("Successfully Updated PaGroupInfoTable decremented VpcCount by 1")
    except Exception as e:
        logger.error("updatePaGroupInfo() Table is failed, Error: {}".format(str(e)))

def getPaGroupInfo(tableName,paGroup):
    """Returns the specified Pagroup item from the PaGroupInfo table
    """
    try:
        table=dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('PaGroupName').eq(paGroup))['Items']
        return response[0]
    except Exception as e:
        logger.error("Fetch Item from PaGroupInfo failed, Error: {}".format(str(e)))

def getItemFromVpcTable(tableName,vpcId):
    """Returns the specified item from VpcTable
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('VpcId').eq(vpcId))
        if response['Items']:
            return response['Items'][0]
        else:
            logger.info("No Item matched with VpcId: {}".format(vpcId))
            return False
    except Exception as e:
        logger.error("Error from getItemFromVpcTable, Error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event {}".format(event))
    #username = "admin"
    #password = "ReanCloud123!"
    config = fetchFromTransitConfigTable(transitConfigTable)
    if config:
        paGroupInfo = getPaGroupInfo(config['TransitPaGroupInfo'],event['PaGroupName'])
        if paGroupInfo:
            api_key = pan_vpn_generic.getApiKey(paGroupInfo['N1Mgmt'], config['UserName'], config['Password'])
            paVpnStatus = pan_vpn_generic.paGroupConfigureVpn(api_key, paGroupInfo, config['TransitVpnBucketName'], event['VpnN1'],event['VpnN2'])
            if paVpnStatus:
                updateVpcTable(config['TransitVpcTable'],event,'Configured')
                data={
                    'Action': 'VpnConfigured',
                    'VpcId': event['VpcId'],
                    'PaGroupName': event['PaGroupName'],
                    'Region': event['Region']
                }
                logger.info("Publishing message to Subscriber SNS with data: {}".format(data))
                publishToSns(event['SubscriberSnsArn'], data, event['SubscriberAssumeRoleArn'])
            else:
                updatePaGroup(config['TransitPaGroupInfo'],event['PaGroupName'], -1)
                updateBgpTunnelIpPool(config['TransitBgpTunnelIpPool'],event['IpSegment'])
                updateVpcTable(config['TransitVpcTable'],event,'Failed')
                #Publish Message to SubscriberSns
                data={
                    'Action': 'VpnFailed',
                    'VpcId': event['VpcId'],
                    'Region': event['Region']
                }
                logger.info("Publishing message to Subscriber SNS with data: {}".format(data))
                publishToSns(event['SubscriberSnsArn'], data, event['SubscriberAssumeRoleArn'])
                #updateVgwAsnTable(config['TransitVgwAsn'],event['VpcId']) #Is this needed, since we are checking for whether vgw is attached to VPC or not in fetchVpnServerDetails
        else:
            logger.error("No Item received from PaGroupInfo table with Key: {}".format(event['PaGroupName']))
    else:
        logger.error("Not Received any data from TransitConfig table")
