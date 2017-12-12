import boto3
import logging
from commonLambdaFunctions import fetchFromSubscriberConfigTable, publishToSns, sendToQueue
from boto3.dynamodb.conditions import Key, Attr
import os, sys

'''
Input:
{
    'Action': 'DeleteVpnConnection',
    'VpnId': 'vpn-xxxxxxxx',
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

def isSubscribingVpcVpn(tableName,vpnId,awsRegion):
    """Verifies whether the VPN connection deleted was associated with Subscribing VPC, if yes, returns VpcId else retruns False
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        response = table.query(KeyConditionExpression=Key('VpnId').eq(vpnId))['Items']
        if response:
            vpcId = response[0]['VpcId']
            ec2_conn = boto3.client('ec2',region_name=awsRegion)
            vpc_tags=ec2_conn.describe_tags(Filters=[{'Name':'resource-id','Values':[vpcId]}],MaxResults=99)['Tags']
            for tag in vpc_tags:
                if tag['Key']==subscribingVpcTag:
                    if tag['Value'].lower()=='yes':
                        return vpcId
        else:
            logger.info("No Item matched in VpcVpnTable with Key: {}, hence exiting".format(vpnId))
            return False
    except Exception as e:
        logger.error("Error from isSubscribingVpcVpn is failed, Error: {}".format(str(e)))
        
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
        logger.info("Updating VPC-Failed tags failed, Error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event: {}".format(event))
    #Loading config from Subsriber Config Table
    subscriberConfig = fetchFromSubscriberConfigTable(subscriberConfigTable)
    if subscriberConfig:
        vpcId = isSubscribingVpcVpn(subscriberConfig['SubscriberVpcVpnTable'],event['VpnId'],event['Region'])
        if vpcId:
            event['Action'] = 'DeleteTransitVpnConfiguration'
            event['VpcId'] = vpcId
            result = deleteItemFromLocalDb(subscriberConfig['SubscriberLocalDb'],vpcId)
            vpn1Id = result['VpnN1']
            vpn2Id = result['VpnN2']
            #Delete Other VPN connection, If the user deletes any of the VPNs
            deleteVpnId = vpn2Id if event['VpnId']==vpn1Id else vpn1Id
            deleteVpn(deleteVpnId,event['Region'])
            deleteVpn(event['VpnId'], event['Region'])

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
            logger.info("VpnId: {} is not associated with any of Subscribing VPCs, hence exiting".format(event['VpnId']))
    else:
        logger.error("No data received from SubscriberConfig Table")
