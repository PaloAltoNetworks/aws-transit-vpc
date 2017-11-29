import sys, os
import boto3
import pan_vpn_generic
from boto3.dynamodb.conditions import Key, Attr
import logging
from commonLambdaFunctions import fetchFromTransitConfigTable, publishToSns, sendToQueue

logger = logging.getLogger()
logger.setLevel(logging.INFO)

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

#transitConfigTable = 'TransitConfig'
#region = 'us-east-1'
'''
pan_vpn_generic.createNewPaGroup(region, stackName, templateUrl, paGroupName, sshKey, transitVpcMgmtAz1, transitVpcMgmtAz2,transitVpcDmzAz1, transitVpcDmzAz2, transitVpcTrustedSecurityGroup, transitVpcUntrustedSecurityGroup,paGroupInstanceProfile, paBootstrapBucketName, Node1Asn, Node2Asn, transitVpcDmzAz1SubnetGateway, transitVpcDmzAz2SubnetGateway )
'''
def updatePaGroup(tableName, paGroup):
    try:
        dynamodb=boto3.resource('dynamodb',)
        table = dynamodb.Table(tableName)
        table.update_item(Key={'PaGroupName':paGroup},AttributeUpdates={'InUse':{'Value':'YES','Action':'PUT'}})
        logger.info("Successfully Updated PaGroupInfoTable attributes InUse=YES")
    except Exception as e:
        logger.error("Error from updatePaGroup, Faild to update table with: {}, Error: {}".format(data,str(e)))
    
def getPaGroupAndAsns(tableName):
    try:
        dynamodb=boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        response=table.scan(FilterExpression=Attr('InUse').eq('NO'))['Items']
        if response:
            updatePaGroup(tableName, response[0]['PaGroupName'])
            return response[0]
        else:
            logger.error("No PaGroups available, Error: {}".format(str(e)))
            sys.exit(0)
    except Exception as e:
        logger.error("Error from updatePaGroup, Error: {}".format(str(e)))    
def lambda_handler(event,context):
    logger.info("Got Event: {}".format(event))
    config = fetchFromTransitConfigTable(transitConfigTable)
    logger.info("TransitConfig Data: {}".format(config))
    if config:
        paGroupTable = config['TransitPaGroupInfo']
        #Get the ANS number for Node1 and Node2
        result = getPaGroupAndAsns(paGroupTable)
        response = pan_vpn_generic.createNewPaGroup(region, result['PaGroupName'],config['PaGroupTemplateUrl'],result['PaGroupName'],config['SshKeyName'],config['TransitVpcMgmtAz1SubnetId'],config['TransitVpcMgmtAz2SubnetId'],config['TransitVpcDmzAz1SubnetId'],config['TransitVpcDmzAz2SubnetId'],config['TransitVpcTrustedSecurityGroupId'],config['TransitVpcUntrustedSecurityGroupId'],config['PaGroupInstanceProfileName'],config['PaBootstrapBucketName'], str(result['N1Asn']), str(result['N2Asn']), config['TransitVpcDmzAz1SubnetGateway'], config['TransitVpcDmzAz2SubnetGateway'])
        response['Region']=region
        response['StackName']=result['PaGroupName']
        logger.info("Sending Data {} to checkStackStaus() function".format(response))
        return response  
    else:
        logger.error("Not Received any data from TransitConfig table")
        return
