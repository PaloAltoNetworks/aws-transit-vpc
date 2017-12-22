import boto3
import logging
from commonLambdaFunctions import fetchFromSubscriberConfigTable, publishToSns, sendToQueue, deleteVgw
from boto3.dynamodb.conditions import Key, Attr
import os, sys

'''
Input:
{
    'Action': 'DeleteVpnConnection',
    'VpcId': 'vpc-xxxxxxxx',
    'Region': '<aws_region>'
}
'''
logger = logging.getLogger()
logger.setLevel(logging.INFO)

subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
subscribingVpcTag = 'subscribingVpc'

transitSnsTopicArn=os.environ['transitSnsTopicArn']
transitAssumeRoleArn=os.environ['transitAssumeRoleArn']

def deleteItemFromLocalDb(tableName, vpcId):
    """Deletes an Item from SubscriberLocalDb table with specified VpcId key
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('VpcId').eq(vpcId))['Items']
        if response:
            table.delete_item(Key={'VpcId':vpcId})
            logger.info("Successfully Deleted Item  with vpc-id : {}".format(vpcId))
            return response[0]
        else:
            logger.info("The Item has been deleted in the Rebalance Operation, hencd exiting from the process")
            sys.exit(0)
    except Exception as e:
        logger.error("Deleting of Item with vpc-id: {}, Error: {}".format(vpcId,str(e)))

def deleteItemFromVpcVpnTable(tableName, vpnId):
    """Deletes an Item from VpcVpnTable with specified VpnId key
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        table.delete_item(Key={'VpnId':vpnId})
        logger.info("Successfully Deleted Item  with vpn-id : {}".format(vpnId))
    except Exception as e:
        logger.error("Error from deleteItemFromVpcVpnTable is failed, Error: {}".format(str(e)))
        
def deleteVpn(vpnId,region):
    """Deletes the VPN Connection associated with the Subscribing VPC
    """
    try:
        ec2_conn = boto3.client('ec2',region_name=region)
        ec2_conn.delete_vpn_connection(VpnConnectionId=vpnId)
        logger.info("Deleted VPN: {} from region: {}".format(vpnId,region))
    except Exception as e:
        logger.error("Error from deleteOtherVpn is failed, Error: {}".format(str(e)))
        pass

def getCgwId(vpnId, awsRegion):
    """Returns CGW id, if the customer gateway is already present/created
    """
    try:
        ec2_conn = boto3.client('ec2',region_name=awsRegion)
        response = ec2_conn.describe_vpn_connections(VpnConnectionIds=[vpnId])['VpnConnections']
        if response: return response[0]['CustomerGatewayId']
        else: return False
    except Exception as e:
        logger.error("Error from getCgwId is failed, Error: {}".format(str(e)))
        pass

def deleteCgw(cgwId, awsRegion):
    """Deletes the CGW
    """
    try:
        ec2_conn = boto3.client('ec2',region_name=awsRegion)
        ec2_conn.delete_customer_gateway(CustomerGatewayId=cgwId)
        logger.info("Deleted CGW: {} from region: {}".format(cgwId,awsRegion))
    except Exception as e:
        logger.error("Error from deleteCgw is failed, Error: {}".format(str(e)))
        pass

def updateTags(awsRegion, vpcId):
    """Updates the tags of VPC with VPN-Deleted, VPN-Removed for keys ConfigStatus and ConfigReason respectively
    """
    try:
        ec2_conn =boto3.client('ec2',region_name=awsRegion)
        tags=[
            {'Key': 'ConfigStatus','Value': 'Vpn-Deleted'},
            {'Key': 'ConfigReason','Value': 'VPN-Removed'}
        ]
        ec2_conn.create_tags(Resources=[vpcId],Tags=tags)
        logger.info("Updated VPC-Failed tags to VPCID: {}".format(vpcId))
    except Exception as e:
        logger.error("Updating VPC-Failed tags failed, Error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event: {}".format(event))
    #Loading config from Subsriber Config Table
    subscriberConfig = fetchFromSubscriberConfigTable(subscriberConfigTable)
    if subscriberConfig:
        vpcId = event['VpcId']
        result = deleteItemFromLocalDb(subscriberConfig['SubscriberLocalDb'],vpcId)
        if 'VpnN1' in result:
            vpn1Id = result['VpnN1']
            vpn2Id = result['VpnN2']
            #deleteVpns
            deleteVpn(vpn1Id,event['Region'])
            deleteVpn(vpn2Id, event['Region'])
        
        # Detach and Delete VGW
        vgwAsn = deleteVgw(result['VgwId'],vpcId,event['Region'])

        event['Action'] = 'DeleteTransitVpnConfiguration'
        if vgwAsn: event['VgwAsn'] = vgwAsn
        #Try to Delete CGWs associated with VPN1 and VPN
        cgw1Id = getCgwId(vpn1Id, event['Region'])
        cgw2Id = getCgwId(vpn2Id, event['Region'])
        try:
            if cgw1Id: deleteCgw(cgw1Id, event['Region'])
            if cgw2Id: deleteCgw(cgw2Id, event['Region'])
        except Exception as e:
            logger.info("Delete Failed for CGWs, Error: {}".format(e))
            pass

        deleteItemFromVpcVpnTable(subscriberConfig['SubscriberVpcVpnTable'], vpn1Id)
        deleteItemFromVpcVpnTable(subscriberConfig['SubscriberVpcVpnTable'], vpn2Id)

        #Update Tags 
        updateTags(event['Region'], vpcId)

        logger.info("Publishing message to TransitSnsArn: {} with data: {}".format(transitSnsTopicArn,event))
        publishToSns(transitSnsTopicArn, str(event), transitAssumeRoleArn)
    else:
        logger.error("No data received from SubscriberConfig Table")
