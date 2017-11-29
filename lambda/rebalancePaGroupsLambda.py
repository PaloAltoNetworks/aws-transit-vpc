import boto3
import os, sys
from boto3.dynamodb.conditions import Key,Attr
from commonLambdaFunctions import fetchFromTransitConfigTable, publishToSns
import logging
import rebalance
import pan_vpn_generic
#transitConfig = os.environ['transitConfigTable']
#transitConfigTable = 'TransitConfig'
#region = 'us-east-1'
transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def updateTransitConfig(tableName, data):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        table.put_item(Item=data)
        logger.info("Updating Trasnit Config with RebalanceStatus with data: {}".format(data))
    except Exception as e:
        logger.error('updateTransitConfig() is Failed, Error: {}'.format(str(e)))

def getSubscriberDataFromVpcTable(tableName, fromPaGroupName):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.scan(FilterExpression=Attr('PaGroupName').eq(fromPaGroupName))
        if 'Items' in response:
            return response['Items'][0]
        else:
            logger.error('No data received for FromPaGroup: {} from VpcTable, hence exiting'.format(fromPaGroupName))
            sys.exit(0)
    except Exception as e:
        logger.error("Error from getSubscriberDataFromVpcTable), Error: {}".format(str(e)))

def checkVpcIdInVpcTable(tableName, vpcId):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('VpcId').eq(vpcId))
        return response
    except Exception as e:
        logger.error("Erro from checkVpcIdInVpcTable(), Error: {}".format(str(e)))

def getInUsePaGroups(tableName, maxCount):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.scan(FilterExpression=Attr('InUse').eq('YES') & Attr('VpcCount').lt(maxCount))
        logger.info("PaGroup Info scan result with Filter InUse=YES and VpcCount < {} is: {}".format(maxCount, response))
        return response['Items']
    except Exception as e:
        logger.error("Error from getInUsePaGroups(), Error: {}".format(str(e)))

def lambda_handler(event, context):
    logger.info("Got Event: {}".format(event))
    config = fetchFromTransitConfigTable(transitConfigTable)
    if config:
        response = getInUsePaGroups(config['TransitPaGroupInfo'], int(config['PaGroupMaxVpc']))
        if response:
            if config['RebalanceInProgress']=='True':
                if config['RebalanceStatus']=='Done':
                    apiKey = pan_vpn_generic.getApiKey(response[0]['N1Mgmt'], config['UserName'], config['Password'])
                    result = rebalance.rebalance(apiKey, response, int(config['PaGroupMaxVpc']), config)
                    if result:
                        # Get the VGW, Region, SubscriberSnsArn and SubscriberAssumeRoleArn from VpcTable
                        subscriberData = getSubscriberDataFromVpcTable(config['TransitVpcTable'], result['FromPaGroup']['PaGroupName'])
                        result['FromPaGroup']['VpcCount'] = str(result['FromPaGroup']['VpcCount'])
                        result['ToPaGroup']['VpcCount'] = str(result['ToPaGroup']['VpcCount'])
                        value = {
                            'FromPaGroupName': result['FromPaGroup']['PaGroupName'],
                            'ToPaGroupName': result['ToPaGroup']['PaGroupName'],
                            'VpcId': subscriberData['VpcId'],
                            'VpcCidr': subscriberData['VpcCidr'],
                            'Region': subscriberData['Region'],
                            'SubscriberSnsArn': subscriberData['SubscriberSnsArn'],
                            'SubscriberAssumeRoleArn' : subscriberData['SubscriberAssumeRoleArn'],
                            'CreateStatus': 'Pending',
                            'DeleteStatus':'InProgress'
                        }
                        item = {'Property': 'RebalanceStatus', 'Value':value}
                        updateTransitConfig(transitConfigTable, item)
                        # Send DeleteOperatin first
                        deleteData = {
                            'Action': 'DeleteVpnConnection',
                            'VpnId': subscriberData['Node1VpnId'],
                            'Region': subscriberData['Region'],
                            'Rebalance': 'True'
                        }
                        #Publish message to Transit SNS
                        publishToSns(subscriberData['SubscriberSnsArn'], deleteData, subscriberData['SubscriberAssumeRoleArn'])
                        logger.info("Published message to Subscriber SNS with data: {}".format(deleteData))
                        return
                else:
                    previousTaskStatus = config['RebalanceStatus']
                    if previousTaskStatus['DeleteStatus']=='InProgress':
                        vpcStatus = checkVpcIdInVpcTable(config['TransitVpcTable'], previousTaskStatus['VpcId'])
                        logger.info("Got VPC Status: {}".format(vpcStatus))
                        if len(vpcStatus['Items'])>0:
                            if vpcStatus['Items'][0]['PaGroupName']==previousTaskStatus['FromPaGroupName']:
                                logger.info("Previous Delete VPN Operation is still InProgress, hence exiting from the process")
                                return
                        else:
                            # Create FetchVpnServerDetails and send to Subscriber SNS
                            previousTaskStatus['CreateStatus'] = 'InProgress'
                            previousTaskStatus['DeleteStatus'] = 'Completed'
                            item = {'Property': 'RebalanceStatus', 'Value':previousTaskStatus}
                            updateTransitConfig(transitConfigTable, item)

                            data = {
                                'Action': 'FetchVpnServerDetails',
                                'Region': previousTaskStatus['Region'],
                                'VpcId': previousTaskStatus['VpcId'],
                                'SubscriberAssumeRoleArn': previousTaskStatus['SubscriberAssumeRoleArn'],
                                'SubscriberSnsArn': previousTaskStatus['SubscriberSnsArn'],
                                'VpcCidr': previousTaskStatus['VpcCidr'],
                                'Rebalance': 'True'
                            }
                            #Publish message to Transit SNS
                            publishToSns(config['TransitSnsArn'], data)
                            logger.info("Published message to Transit SNS with data: {}".format(data))
                            return
                    elif previousTaskStatus['CreateStatus']=='InProgress':
                        logger.info("Previous task was CreateTask, now check whether it has completed or not")
                        vpcStatus = checkVpcIdInVpcTable(config['TransitVpcTable'], previousTaskStatus['VpcId'])
                        logger.info("Got VPC Status: {}".format(vpcStatus))
                        if not vpcStatus['Items']:
                            logger.info("Create Task is still in progress, hence exiting")
                            return
                        else:
                             if vpcStatus['Items'][0]['PaGroupName'] == previousTaskStatus['ToPaGroupName']:
                                 logger.info("Previous Rebalance task Completed successfully, updating the RebalanceStatus=Done")
                                 item = {'Property': 'RebalanceStatus', 'Value':'Done'}
                                 updateTransitConfig(transitConfigTable, item)
                                 return
                             else:
                                 logger.error("Something terrible happened? Unknown status, Stop StateMachine and Exit")
                                 #Something terrible happened? Unknown status, Stop StateMachine and Exit
                                 return
        else:
            logger.info("No PaGroups for Rebalancing, PaGroups are Optimal")
    else:
        logger.error("Not Received any data from TransitConfig table")
