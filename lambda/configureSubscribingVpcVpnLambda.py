import boto3
from boto3.dynamodb.conditions import Key, Attr
import logging, os, sys
from commonLambdaFunctions import createVpnConnectionUploadToS3, fetchFromSubscriberConfigTable, createVgwAttachToVpc, createCgw, publishToSns, isVgwAttachedToVpc, checkCgw

logger = logging.getLogger()
logger.setLevel(logging.INFO)

'''
Input:
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
    'VpcCidr': event['VpcCidr'],
    'Region': event['Region'],
    'TransitVpnBucketName': transitConfig['TransitVpnBucketName'],
    'TransitAssumeRoleArn': transitConfig['TransitAssumeRoleArn'],
    'TransitSnsArn': transitConfig['TransitSnsArn']
} 
'''

subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
        
def putItemSubscriberLocalDb(tableName,item):
    """Puts an Item into the SubscriberLocalDb table with VpcId, VpcCidr, VgwId, Cgw1Id, Cgw2Id, Vpn1Id, Vpn2Id and PaGroupName
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        table.put_item(Item=item)
        logger.info("Updating LocalDb with data: {}".format(item))
    except Exception as e:
        logger.error("Updating LocalDb failed, Error: {}".format(str(e)))

def updateVpcVpnTable(tableName,item):    
    """Updates VpcVpnTable with VpnId, VpcId, PaGroupName and PaGroupNode
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        table.put_item(Item=item)
        logger.info("Updating VpcVpnTable is success with data: {}".format(item))
    except Exception as e:
        logger.error("Updating VpcVpnTable failed, Error: {}".format(str(e)))

def lambda_handler(event,context):
    logger.info("Got Event {}".format(event))
    try:
        subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
        if subscriberConfig:
            vgwId = isVgwAttachedToVpc(event['VpcId'], event['Region'])
            if not vgwId:
                #Create VGW and attach it to VPC
                if 'VgwAsn' in event:
                    vgwId=createVgwAttachToVpc(event['VpcId'],int(event['VgwAsn']),event['Region'],event['PaGroupName'])
                    logger.info("VGW - {} is created and attached to VPC - {}".format(vgwId,event['VpcId']))
            logger.info("Checking whether CGWs are already created or not")
            cgwIds = checkCgw(event['Region'],event['N1Eip'], event['N2Eip'])
            if not cgwIds:
                #Create CGW1
                cgw1Tag=event['PaGroupName']+'-N1'
                cgwNode1Id=createCgw(event['N1Eip'],event['N1Asn'],event['Region'],cgw1Tag)
                logger.info("CGW - {} is created for VPC - {}".format(cgwNode1Id,event['VpcId']))
                #Create CGW2
                cgw2Tag=event['PaGroupName']+'-N2'
                cgwNode2Id=createCgw(event['N2Eip'],event['N2Asn'],event['Region'],cgw2Tag)
                logger.info("CGW - {} is created for VPC - {}".format(cgwNode1Id,event['VpcId']))
            else:
                logger.info("CGWs are already created, CgwNode1Id: {}, CgwNode2Id: {}".format(cgwIds[0], cgwIds[1]))
                cgwNode1Id = cgwIds[0]
                cgwNode2Id = cgwIds[1]

            # VPN Connection
            print(event['PaGroupName'])
            vpn1Tag=event['VpcId']+'-'+event['PaGroupName']+'-N1'
            vpn2Tag=event['VpcId']+'-'+event['PaGroupName']+'-N2'
            #Create VPN1 connection with Node1
            if vgwId: vpnId1=createVpnConnectionUploadToS3(event['Region'],vgwId,cgwNode1Id,event['N1T1'],event['N1T2'],vpn1Tag,event['TransitVpnBucketName'],event['TransitAssumeRoleArn'])
            logger.info("VPN1 - {} is created for VPC - {} with PA-Group: {}".format(vpnId1,event['VpcId'],event['PaGroupName']))
            #Crete VPN2 connection with Node2
            if vgwId: vpnId2=createVpnConnectionUploadToS3(event['Region'],vgwId,cgwNode2Id,event['N2T1'],event['N2T2'],vpn2Tag,event['TransitVpnBucketName'],event['TransitAssumeRoleArn'])
            logger.info("VPN2 - {} is created for VPC - {} with PA-Group: {}".format(vpnId2,event['VpcId'],event['PaGroupName']))
            #Forming an output to sent to TransitSNSTopic
            if vpnId1 and vpnId2:
                data={
                    'Action': 'ConfigureTransitVpn',
                    'PaGroupName': event['PaGroupName'],    
                    'IpSegment': event['IpSegment'],
                    'VpnN1': vpnId1,
                    'VpnN2': vpnId2,
                    'VpcId': event['VpcId'],
                    'Region': event['Region'],
                    'Rebalance': event['Rebalance'],
                    'TransitVpnBucketName': event['TransitVpnBucketName'],
                    'SubscriberSnsArn': subscriberConfig['SubscriberSnsArn'],
                    'SubscriberAssumeRoleArn': subscriberConfig['SubscriberAssumeRoleArn']
                }
                if 'ToPaGroup' and 'FromPaGroup' in event:
                    data['ToPaGroup'] = event['ToPaGroup']
                    data['FromPaGroup'] = event['FromPaGroup']
                    #data['Action'] = 'RebalanceConfigureTransitVpn'
                #Publish message to TransitSNSTopic
                publishToSns(event['TransitSnsArn'], data, event['TransitAssumeRoleArn'])
                logger.info("Publishing message to Transit SNS - {} with data: {}".format(event['TransitSnsArn'],data))
            #Update SubcriberDynamoDB with VPN1-ID, VPN1-ID, VGW, CGW1, CGW2 and PA-Group-Name
            if vpnId1 and vpnId2: 
                data = {
                    'VpcId': event['VpcId'],
                    'VpcCidr': event['VpcCidr'],
                    'Region': event['Region'],
                    'VgwId': vgwId,
                    'PaGroupName': event['PaGroupName'],
                    'CgwN1': cgwNode1Id,
                    'CgwN2': cgwNode2Id,
                    'VpnN1': vpnId1,
                    'VpnN2': vpnId2
                }
                putItemSubscriberLocalDb(subscriberConfig['SubscriberLocalDb'], data)
            #Update VpcVPnTable with VpnId, VpcId, PaGroup, PaGroupNode
            if vpnId1:
                data = {
                    'VpnId': vpnId1,
                    'VpcId': event['VpcId'],
                    'PaGroupName': event['PaGroupName'],
                    'PaGroupNode': event['N1Eip']
                }
                updateVpcVpnTable(subscriberConfig['SubscriberVpcVpnTable'],data)
            if vpnId2: 
                data = {
                    'VpnId': vpnId2,
                    'VpcId': event['VpcId'],
                    'PaGroupName': event['PaGroupName'],
                    'PaGroupNode': event['N2Eip']
                }
                updateVpcVpnTable(subscriberConfig['SubscriberVpcVpnTable'],data)
            #Publish message to Transit VPN
        else:
            logger.error("No data received from SubscriberConfig Table, Error")
    except Exception as e:
        logger.error("Error from subscriberVpn Configuration, Error: {}".format(str(e)))
        #If Something fails
        #Send TransitSNS with action “SubscriberVpnConfigurationFailed” to release reserved capacity
        data={
            'Action': 'SubscriberVpnConfigurationFailed',
            'PaGroupName': event['PaGroupName'],
            'VpcId' : event['VpcId'],
            'SubscriberSns' : subscriberConfig['SubscriberSnsArn'],
            'IpSegment': event['IpSegment']
        }
        logger.info("Publishing message to Transit SNS with subject SubscriberVpnConfigurationFailed, because of Error: {}".format(str(e)))
        publishToSns(event['TransitSnsArn'], data, event['TransitAssumeRoleArn'])
