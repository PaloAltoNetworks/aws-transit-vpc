import boto3
from boto3.dynamodb.conditions import Key, Attr
import logging, os
from commonLambdaFunctions import fetchFromTransitConfigTable

logger = logging.getLogger()
logger.setLevel(logging.INFO)
'''
Input:
{
    'Action': 'SubscriberVpnConfigurationFailed',
    'PaGroupName': event['PaGroupName'],
    'VpcId' : event['VpcId']
    'SubscriberSns' : subscriberSnsTopicArn,
    'IpSegment': event['IpSegment']
}
Does:
    Update Dynamodb table with ip-pool to available and reduced the pa-group count
'''

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

dynamodb = boto3.resource('dynamodb', region_name=region)

def updateBgpTunnelIpPool(bgpTableName,ipSegment):
    """Updates the Transit BgpTunnelIpPool table attributes Available=YES by specifying the IpSegment primary key
    """
    try:
        table=dynamodb.Table(bgpTableName)
        #Update BgpTunnelIpPool table Attribute "Available"="YES"
        table.update_item(Key={'IpSegment':ipSegment},AttributeUpdates={'Available':{'Value':'YES','Action':'PUT'}})
        logger.info("Successfully Updated BgpIpPoolTable attribute Available=YES")
    except Exception as e:
        logger.error("Error from updateBgpTunnelIpPool(), Error: {}".format(str(e)))
        
def updatePaGroup(paGroupTableName,paGroupName):
    """Updates the Transit PaGroupInfo table attributes InUse=YES and  VpcCount value decrement by 1 (VpcCount=VpcCount-1) by specifying the PaGroupName primary key
    """
    try:
        table=dynamodb.Table(paGroupTableName)
        table.update_item(Key={'PaGroupName':paGroupName},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'},'VpcCount':{'Value':-1,'Action':'ADD'}})
        logger.info("Successfully Updated PaGroupInfoTable decremented VpcCount")
    except Exception as e:
        logger.error("Error from updatePaGroup(), Error: {}".format(str(e)))

def updateVgwAsn(tableName,vgwAsn):
    """Updates Transit VgwAsn table attribute "InUse=NO"
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        logger.info("VgwAsn TableName: {}, and typeofVgwAsn: {}".format(tableName,type(vgwAsn)))
        response = table.query(KeyConditionExpression=Key('VgwAsn').eq(str(vgwAsn)))['Items']
        if response:
           item={'VgwAsn':str(vgwAsn),'InUse':'NO'}
           table.put_item(Item=item)
           logger.info("Successfully updated VgwAsn: {}, InUse=NO".format(vgwAsn))
    except Exception as e:
        logger.error("Error from updatePaGroupInfoTable, Error: {}".format(str(e)))
        #If the VGW was created by customer manually, we dont have that VgwAsn enrty in Transit VgwAsn table, hence we are throwing the error and proccedind
        pass

def lambda_handler(event,context):
    transitConfig=fetchFromTransitConfigTable(transitConfigTable)
    updatePaGroup(transitConfig['TransitPaGroupInfo'],event['PaGroupName'])
    updateBgpTunnelIpPool(transitConfig['TransitBgpTunnelIpPool'],event['IpSegment'])
    updteVgwAsn(transitConfig['TransitVgwAsn'], event['VgwAsn'])
