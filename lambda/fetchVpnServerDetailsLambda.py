import boto3
from boto3.dynamodb.conditions import Key, Attr
import logging
import os
from commonLambdaFunctions import fetchFromTransitConfigTable, publishToSns, sendToQueue
import sys


logger = logging.getLogger()
logger.setLevel(logging.INFO)

'''
Input:
{
    'Action'                    : 'FetchVpnServerDetails',
    'VpcId'                     : 'vpc-xxxxxxx',
    'VpcCidr'                   : 'v.w.x.y/z',
    'Region'                    : 'AWS_Region',
    'SubscriberAssumeRoleArn'   : '<IamRoleArn>',
    'SubscriberSnsArn'           : '<SnsTopiArn>',
    'Rebalance'                 : 'False/True'
}
Output:
{
    'Action': 'ConfigureSubscribingVpcVpn',
    'IpSegment': bgpIpPool['IpSegment'],
    'N1T1': bgpIpPool['N1T1'],
    'N1T2': bgpIpPool['N1T2'], 
    'N1Eip': paGroup['N1Eip'],
    'N1Asn': paGroup['N1Asn'],
    'N2T1': bgpIpPool['N2T1'],
    'N2T2': bgpIpPool['N2T2'], 
    'N2Eip': paGroup['N2Eip']'
    'N2Asn': paGroup['N2Asn'],
    'PaGroupName': paGroup['PaGroupName'],
    'Rebalance' : 'False',
    'VpcId': event['VpcId'],
    'TransitVpnBucketName': transitConfig['TransitVpnBucketName'],
    'TransitAssumeRoleArn': transitConfig['TransitAssumeRoleArn'],
    'TransitSnsArn': transitConfig['TransitSnsArn']
} 
'''

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']
dynamodb = boto3.resource('dynamodb',region_name=region)

def checkVpcCidrConflicts(vpcCidr,tableName):
    """Check whether there is a VPCCIDR conflict:
    If yes send notification back to Subscriber SNS that Vpn configuration failed
    Create log VPCCIDR conflict “New VPCID, NewVPC CIDR, Existing VPCID, Existing VPCCIDR
    """
    try:
        table=dynamodb.Table(tableName)
        response=table.scan(FilterExpression=Attr('VpcCidr').eq(vpcCidr))['Items']
        logger.info("Scan results of VpcTable: {}".format(response))
        if not response:
            return True
        return False
    except Exception as e:
        logger.error("Checking of CIDR confilcts failed, Error: {}".format(str(e)))

def getAvailableBgpTunnelIpPool(tableName, vpcId, paGroupName):
    """Scans the BgpTunnleIpPool table with attribute 'Avaliable=YES', if it finds any items with this condition returns that item otherwise returns false
    Calls the updateBgpTunnleIpPool function to update the attribute 'Available' to NO
    """
    try:
        logger.info("Fetching BgpTunnelIpPool data with fileter status=available")
        table=dynamodb.Table(tableName)
        response=table.scan(FilterExpression=Attr('Available').eq('YES'))['Items']
        if response:
            #Update BgpTunnelIpPool table Attribute "Available"="NO"
            updateBgpTunnelIpPool(response[0]['IpSegment'],table, vpcId, paGroupName)
            return response[0]
        else:
            return False
    except Exception as e:
        logger.error("getAvailableBgpTunnelIpPool failed, Error: {}".format(str(e)))
    
def getAvailablePaGroup(tableName,maxCount):
    """Scans the PaGroupInfo table with attributes 'InUse=YES' and 'VpcCount' less than MaxPaGroupCapacity, if it finds an items it will return that item, otherwise 
    Otherwise: it scans the table with attribute 'InUse=NO', if it finds an item it will return othrwise returns False
    Calls updatePaGroup() function to update the 'InUse' to YES and increment the VpcCount by +1
    """
    try:
        table=dynamodb.Table(tableName)
        response=table.scan(FilterExpression=Attr('InUse').eq('YES') & Attr('VpcCount').lt(maxCount))['Items']
        logger.info("PaGroup Info scan result with Fileter InUse=YES and VpcCount < {} is: {}".format(maxCount, response))
        if response:
            #Logic to return the PaGroup which has nearest capacity 
            value=response[0]['VpcCount']
            paGroupToReturn=response[0]
            for item in response:
                if 'N1Eip' in item:
                    if value<item['VpcCount']:
                        value=item['VpcCount']
                        paGroupToReturn=item
                else:
                    return False
            logger.info("Returing the Pa Group which has nearest capacity, PA-Group Name: {}".format(paGroupToReturn['PaGroupName']))
            #Update PaGroupInfo Table InUse="Yes" and increment VpcCount+1
            updatePaGroup(paGroupToReturn['PaGroupName'],table)
            return paGroupToReturn
        else:
            response=table.scan(FilterExpression=Attr('InUse').eq('NO'))['Items']
            if response:
                for group in response:
                    if 'N1Eip' in group:
                        #Update PaGroupInfo Table InUse="Yes" and increment VpcCount+1
                        logger.info("Returing the PA-Group Name: {}".format(group['PaGroupName']))
                        updatePaGroup(group['PaGroupName'],table)
                        return group
                else:
                    return False
            else:
                return False
    except Exception as e:
        logger.error("getAvailablePaGroup is failed, Error: {}".format(str(e)))

def getAvailableVgwAsn(tableName,data):
    """Scans the VgwAsn table with attribute 'InUse=NO', if it finds an item it will return that item, otherwise exit from the process
    Calls updateVgwAnsTable() function to update the 'InUse' to YES and VpcId and VpcCidr
    """
    try:
        table=dynamodb.Table(tableName)
        response=table.scan(FilterExpression=Attr('InUse').eq('NO'))['Items']
        if response:
            #Update VgwAsn Table with InUse=YES, VpcId and VpcCidr values
            result = updateVgwAsnTable(response[0]['VgwAsn'],data,table)
            return response[0]['VgwAsn']
        else:
            logger.error("VgwAsn numbers are exhausted, so Pleas add some more ASN numbers to VgwAsn Table")
            sys.exit(0)
    except Exception as e:
        logger.error("getAvailableVgwAsn is failed, Error: {}".format(str(e)))
        
def updateBgpTunnelIpPool(ipSegment,tableConn, vpcId, paGroupName):
    """Updates the BgpTunnelIpPool table attributes Available=NO, and add VpcId and PaGroup names to the item
    """
    try:
        #Update BgpTunnelIpPool table Attribute "Available"="NO"
        tableConn.update_item(Key={'IpSegment':ipSegment},AttributeUpdates={'Available':{'Value':'NO','Action':'PUT'}, 'VpcId': {'Value':vpcId, 'Action':'PUT'}, 'PaGroupName':{'Value':paGroupName, 'Action':'PUT'}})
        logger.info("Successfully Updated BgpIpPoolTable attribute Available=NO, VpcId: {} and PaGroupName: {}".format(vpcId, paGroupName))
    except Exception as e:
        logger.error("Error from updateBgpTunnelIpPool, {}".format(str(e)))
        
def updatePaGroup(paGroupName,tableConn):
    """Updates the Transit PaGroupInfo table with InUse=YES and increments the VpcCount by +1
    """
    try:
        tableConn.update_item(Key={'PaGroupName':paGroupName},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'},'VpcCount':{'Value':1,'Action':'ADD'}})
        logger.info("Successfully Updated PaGroupInfoTable attributes InUse=YES and incremented VpcCount")
    except Exception as e:
        logger.error("Error from updatePaGroup, {}".format(str(e)))
        
def updateVgwAsnTable(id,data,tableConn):
    """Updates Transit VgwAsn table with VpcId, VpcCidr, an InUse=YES
    """
    try:
        #Update VgwAsn Table with InUse=YES, VpcId and VpcCidr values
        tableConn.update_item(Key={'VgwAsn':id},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'},'VpcId':{'Value':data['VpcId'],'Action':'PUT'},'VpcCidr':{'Value':data['VpcCidr'],'Action':'PUT'}})
        logger.info("Successfully Updated VgwAsnTable attributes InUse=YES and VpcId: {}, VpcCidr:{}".format(data['VpcId'],data['VpcCidr']))
    except Exception as e:
        logger.error("Error from updateVgwAsnTable, {}".format(str(e)))
    
def updateVpcTable(tableName,data,paGroupName):
    """Updates the Transit VpcTable with VpcId, VpcCidr, Region, SubscriberSnsArn, SubscriberAssumeRoleArn, PaGroupName and CurrentStatus of VPN connection
    """
    try:
        #VpcCidr is the primary key for VpcTable
        table=dynamodb.Table(tableName)
        item={
            'VpcId': data['VpcId'],
            'VpcCidr': data['VpcCidr'],
            'Region': data['Region'],
            'SubscriberSnsArn': data['SubscriberSnsArn'],
            'SubscriberAssumeRoleArn': data['SubscriberAssumeRoleArn'],
            'PaGroupName': paGroupName,
            'CurrentStatus': 'Inprogress'
        }
        response=table.put_item(Item=item)
    except Exception as e:
        logger.error("Updating Transit VpcTalbe is Failed, Error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event: {}".format(event))
    paloAltoGroupCapacity=os.environ['paloAltoGroupCapacity']
    try:
        transitConfig=fetchFromTransitConfigTable(transitConfigTable)
        if transitConfig:    
            subscriberSnsTopicArn=event['SubscriberSnsArn']
            subscriberAssumeRoleArn=event['SubscriberAssumeRoleArn']
            
            #TransitTaskHandler data event
            transitTaskHandler={'Action': 'TransitTaskHandler'}
            
            #Check VPC CIDR Conflicts
            result=checkVpcCidrConflicts(event['VpcCidr'],transitConfig['TransitVpcTable'])
            if result:
            #Get Available PA-Group
                paGroup=getAvailablePaGroup(transitConfig['TransitPaGroupInfo'],int(transitConfig['PaGroupMaxVpc']))
                if paGroup:
                    logger.info("Got PaGroup Details {} , hence proceeding to get available VGW ASN Number ".format(paGroup))
                    #Get Available VgwAsn Number
                    vgwAsnNumber = ""
                    if 'Rebalance' in event and event['Rebalance']!='True':
                        vgwAsnNumber=getAvailableVgwAsn(transitConfig['TransitVgwAsn'],event)
                        logger.info("Got vgwAsnNumber={}, hence proceeding to get available BgpIpPool Cidr ranges".format(vgwAsnNumber))
                    #Get Available Tunnel IP Pool Ranges
                    bgpIpPool=getAvailableBgpTunnelIpPool(transitConfig['TransitBgpTunnelIpPool'], event['VpcId'], paGroup['PaGroupName'])
                    if bgpIpPool:
                        logger.info("Got bgpIpPool={}, hence proceeding to publish to Subscriber-SNS ".format(bgpIpPool))
                        data={
                            'Action': 'ConfigureSubscribingVpcVpn',
                            'IpSegment': bgpIpPool['IpSegment'],
                            'N1T1': bgpIpPool['N1T1'],
                            'N1T2': bgpIpPool['N1T2'], 
                            'N1Eip': paGroup['N1Eip'],
                            'N1Asn': str(paGroup['N1Asn']),
                            'N2T1': bgpIpPool['N2T1'],
                            'N2T2': bgpIpPool['N2T2'], 
                            'N2Eip': paGroup['N2Eip'],
                            'N2Asn': str(paGroup['N2Asn']),
                            'PaGroupName': paGroup['PaGroupName'],
                            'Rebalance' : event['Rebalance'],
                            'VpcId': event['VpcId'],
                            'VpcCidr': event['VpcCidr'],
                            'Region': event['Region'],
                            'TransitVpnBucketName': transitConfig['TransitVpnBucketName'],
                            'TransitAssumeRoleArn': transitConfig['TransitAssumeRoleArn'],
                            'TransitSnsArn': transitConfig['TransitSnsArn']
                        } 
                        if vgwAsnNumber: data['VgwAsn'] = str(vgwAsnNumber)
                        #Update VpcTable with VpcId, VpcCidr and SubsriberSnsArn
                        updateVpcTable(transitConfig['TransitVpcTable'],event,paGroup['PaGroupName'])
                        #Publish the data to Subscriber-SNS Topic
                        logger.info("Publishing to Subscriber SNS: {} with data: {}".format(subscriberSnsTopicArn,data))
                        publishToSns(subscriberSnsTopicArn,data,subscriberAssumeRoleArn)
                        return transitTaskHandler
                    else:
                        logger.error("BgpTunnelIpPools are exausted, hence exiting from setup")
                        sys.exit(0)
                else:
                    #Launch CFT to spin up new PA-Group 
                    #Update the PaGroupInfo table with PaGroup, N1Asn, N2Asn, InUse, N1Mgmt, N2Mgmt, N1Eip, N2Eip, VpcCount
                    logger.info("PA-Groups are exausted, hence pushing the message back to Queue and passing control to CreateNewPaGroup function")
                    '''
                      A FIFO message uses a MessageDeduplicationId key to manage deduplication of sent messages. Every message must have a unique MessageDeduplicationId. If a message with a particular MessageDeduplicationId is sent successfully, any messages sent with the same MessageDeduplicationId will not be delivered during the five-minute deduplication window
                    '''
                    #To Avoid Message DedupliationId to be same, we are adding one more Key:Value pair to the event
                    event['ReceivedFrom']='fetchVpnServerDetails'
                    sendToQueue(transitConfig['TransitNormalQueue'],str(event),event['Action'])
                    data={
                        'Action':'CreateNewPaGroup',
                        'Rebalance': event['Rebalance']
                    }
                    return data        
            else:
                logger.info("Conflicts with VPC CIDR, NewVpcId={}, NewVpcCidr={}".format(event['VpcId'],event['VpcCidr']))
                data={
                    'Action': 'VpnFailed',
                    'Reason': 'VPC-CIDR Conflicts'
                }
                logger.info("Publishing to Subscriber SNS: {} with data: {}".format(subscriberSnsTopicArn,data))
                publishToSns(subscriberSnsTopicArn,data,subscriberAssumeRoleArn)
        else:
            logger.error("Not Received any data from TransitConfig table")
    except Exception as e:
        logger.error("Error: {}".format(str(e)))
