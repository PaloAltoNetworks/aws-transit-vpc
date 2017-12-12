import boto3
import logging, os
import pan_vpn_generic
import sys, traceback
from commonLambdaFunctions import fetchFromTransitConfigTable, publishToSns
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

def deleteItemFromVpcTable(tableName, vpcId):
    """Deletes an Item from Transit VpcTable by specifying the VpcId key
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        table.delete_item(Key={'VpcId':vpcId})
        logger.info("Successfully Deleted Item  with vpc-id: {} from TransitVpcTable".format(vpcId))
    except Exception as e:
        logger.error("Error from deleteItemFromVpcTable, Error: {}".format(str(e)))

def updatePaGroupInfoTable(tableName,paGroupName):
    """Updates the Transit PaGroupInfo table  attribute VpcCount value to decremented by 1 (-1) by querying the table with PaGroupName
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('PaGroupName').eq(paGroupName))['Items']
        if response:
            if response[0]['VpcCount']>0:
                table.update_item(Key={'PaGroupName':paGroupName},AttributeUpdates={'VpcCount':{'Value':-1,'Action':'ADD'}})
                logger.info("Successfully decremented PaGroup: {} VpcCount to -1".format(paGroupName))
    except Exception as e:
        logger.error("Error from updatePaGroupInfoTable, Error: {}".format(str(e)))

def updateBgpTunnleIpPool(tableName,paGroupName):
    """Updates the Transit BgpTunnleIpPool attributes Available=YES, VpcId=Null and PaGroupName=Null
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.scan(FilterExpression=Attr('PaGroupName').eq(paGroupName))
        LastEvaluatedKey = True
        while LastEvaluatedKey:
            for item in response['Items']:
                if 'PaGroupName' in item:
                    if item['PaGroupName']==paGroupName:
                        table.update_item(Key={'IpSegment':item['IpSegment']},AttributeUpdates={'Available':{'Value':'YES','Action':'PUT'},'VpcId':{'Value':'Null','Action':'PUT'},'PaGroupName':{'Value':'Null','Action':'PUT'}})
                        logger.info("Successfully updated IpSegment: {} attriburte Available to YES, and VpcId & PaGroup to Null".format(item['IpSegment']))
                        return
            if 'LastEvaluatedKey' in response:
                response = table.scan(FilterExpression=Attr('PaGroupName').eq(paGroupName),ExclusiveStartKey=response['LastEvaluatedKey'])
            else:
                LastEvaluatedKey = False
    except Exception as e:
        logger.error("Error from updateBgpTunnleIpPool, Error: {}".format(str(e)))

def getItemFromVpcTable(tableName,vpcId):
    """Returns an Item from Transit VpcTable by querying the table with VpcId key
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

def getItemFromPaGroupInfo(tableName, paGroupName):
    """Returns an Item from PaGroupInfo table by querying the table with PaGroupName key
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('PaGroupName').eq(paGroupName))
        if response['Items']:
            return response['Items'][0]
        else:
            logger.info("No Items matched with the GropuName: {}".format(paGroupName))
            return False
    except Exception as e:
        logger.error("Error from getItemFromPaGroupInfo, Error: {}".format(str(e)))


def lambda_handler(event,context):
    logger.info("Got Event: {}".format(event))
    try:
        config = fetchFromTransitConfigTable(transitConfigTable)
        if config:
            #deleteVpnConfigurationFromPaGroup() this will be from pan_vpn_generic file
            vpcResult = getItemFromVpcTable(config['TransitVpcTable'],event['VpcId'])
            if vpcResult:
                paGroupResult = getItemFromPaGroupInfo(config['TransitPaGroupInfo'],vpcResult['PaGroupName'])
                if paGroupResult:
                    api_key = pan_vpn_generic.getApiKey(paGroupResult['N1Mgmt'], config['UserName'],config['Password'])
                    #Deleting the VPN connections with the PA Group
                    pan_vpn_generic.paGroupDeleteVpn(api_key, paGroupResult, vpcResult['Node1VpnId'],vpcResult['Node2VpnId'])
                    logger.info("Successfully deleted VPN connections VPN1: {}, VPN2: {} with PaGroup: {} ".format(vpcResult['Node1VpnId'],vpcResult['Node2VpnId'],paGroupResult['PaGroupName']))
                    #Delete Item from TransitVpcTable with 
                    deleteItemFromVpcTable(config['TransitVpcTable'],event['VpcId'])
                    updatePaGroupInfoTable(config['TransitPaGroupInfo'],vpcResult['PaGroupName'])
                    updateBgpTunnleIpPool(config['TransitBgpTunnelIpPool'], vpcResult['PaGroupName'])
        else:
            logger.error("Not Received any data from TransitConfig table")
    except Exception as e:
        logger.error("Error from deleteTransitVpnConfiguration, Error: {}".format(str(e)))
