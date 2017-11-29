import boto3
import logging, os
import pan_vpn_generic
from commonLambdaFunctions import fetchFromTransitConfigTable
from boto3.dynamodb.conditions import Key, Attr

#import time
'''
Input:
{
    'StackName': 'someName',
    'StackId': 'Stack_ID'
    'Region': 'AwsRegion'
}
Output:
{
    'Action': 'Success/Wait/None'
}
'''

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#transitConfigTable = "TransitConfig"
#region = 'us-east-1'

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

def updateConfigDb(data):
    try:

        item = {'Property':'StackError', 'Value':'Error While Creating Stack {}'.format(data)}
        dynamodb=boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(transitConfigTable)
        table.put_item(Item=item)

    except Exception as e:
        logger.error("Error from updateConfigDb, Error: {}".format(str(e)))

def updatePaGroup(tableName, data, awsRegion):
    try:

        dynamodb=boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        table.update_item(Key={'PaGroupName':data['PaGroupName']},AttributeUpdates={'N1Mgmt':{'Value':data['N1Mgmt'],'Action':'PUT'},'N2Mgmt':{'Value':data['N2Mgmt'],'Action':'PUT'}, 'N1Eip':{'Value':data['N1Eip'],'Action':'PUT'},'N2Eip':{'Value':data['N2Eip'],'Action':'PUT'},'N1Pip':{'Value':data['N1Pip'],'Action':'PUT'},'N2Pip':{'Value':data['N2Pip'],'Action':'PUT'}, 'StackRegion':{'Value': awsRegion,'Action':'PUT'}})

    except Exception as e:
        logger.error("Error from updatePaGroup, Faild to update table with: {}, Error: {}".format(data,str(e)))

def configurePaPeers(tableName,apiKey, newGroup):
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        response = table.scan(FilterExpression=Attr('InUse').eq('YES'))['Items'] 
        if response:
            paPeerStatus = pan_vpn_generic.paGroupSetupPaPeers(apiKey,newGroup,response)
            if paPeerStatus:
                logger.info("Peering of new PA Group: {}, with other PAGroups is Done".format(newGroup))
        else:
            logger.info("No other PA Groups to configure Peering")
    except Exception as e:
        logger.error("Error from configurePaPeers, error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event {}".format(event))
    config = fetchFromTransitConfigTable(transitConfigTable)

    if config:
        stackStatus = pan_vpn_generic.parseStackOutput(event['StackName'],event['Region'])
        logger.info("Stack Status: {}".format(stackStatus))

        if 'PaGroupName' in stackStatus:
            panStatus=pan_vpn_generic.checkPaGroupReady(config['UserName'],config['Password'],stackStatus)

            if panStatus:
                logger.info("PaGroup: {} is ready".format(stackStatus['PaGroupName']))
                logger.info("Initializing the PA Servers")
                api_key = pan_vpn_generic.getApiKey(stackStatus['N1Mgmt'], config['UserName'], config['Password'])
                initPaServersStatus = pan_vpn_generic.paGroupInitialize(api_key, stackStatus, config['DeLicenseApiKey'])

                if initPaServersStatus:

                    logger.info("Initialization of PA Servers is Success, response: {}".format(initPaServersStatus))                        
                    logger.info("Updating PaGroupInfoTable with PaGroup, N1Mgmt, N2Mgmt, N1Eip, N2Eip and VpcCount=0")
                    updatePaGroup(config['TransitPaGroupInfo'], stackStatus, event['Region'])
                    import time
                    time.sleep(5)
                    logger.info("Peering of PA Groups with new PAGroup initiated")
                    configurePaPeers(config['TransitPaGroupInfo'],api_key, stackStatus)
                    event['Action']='Success'
                    return event
                else:
                    logger.info("Initialization of PA Servers is failed, Error {}".format(initPaServerStatus))
                    event['Action']='Error While Initializing the PA Server {}'.format(stackStatus)
                    return event
            else:
                logger.info("PaGroup: {} is NOT ready".format(stackStatus['PaGroupName']))
                event['Action']='Wait'
                return event
        elif stackStatus=="Wait":
            event['Action']='Wait'
            return event
        else:
            updateConfigDb(event['StackName'])
            return
    else:
        logger.error("Not Received any data from TransitConfig table")
        return
