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
#transitConfigTable = "TransitConfig"
#transitBgpTunnelIpPoolTable = "TransitBgpTunnelIpPool"

def updateBgpTunnelIpPool(bgpTableName,ipSegment):
    try:
        table=dynamodb.Table(bgpTableName)
        #Update BgpTunnelIpPool table Attribute "Available"="YES"
        table.update_item(Key={'IpSegment':ipSegment},AttributeUpdates={'Available':{'Value':'YES','Action':'PUT'}})
        logger.info("Successfully Updated BgpIpPoolTable attribute Available=YES")
    except Exception as e:
        logger.error("Error from updateBgpTunnelIpPool(), Error: {}".format(str(e)))
        
def updatePaGroup(paGroupTableName,paGroupName):
    try:
        table=dynamodb.Table(paGroupTableName)
        table.update_item(Key={'PaGroupName':paGroupName},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'},'VpcCount':{'Value':-1,'Action':'ADD'}})
        logger.info("Successfully Updated PaGroupInfoTable decremented VpcCount")
    except Exception as e:
        logger.error("Error from updatePaGroup(), Error: {}".format(str(e)))

def lambda_handler(event,context):
    transitConfig=fetchFromTransitConfigTable(transitConfigTable)
    updatePaGroup(transitConfig['TransitPaGroupInfo'],event['PaGroupName'])
    updateBgpTunnelIpPool(transitConfig['TransitBgpTunnelIpPool'],event['IpSegment'])
