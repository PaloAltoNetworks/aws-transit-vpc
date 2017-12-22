import boto3
import logging
import json
import os, sys
from boto3.dynamodb.conditions import Key, Attr
from commonLambdaFunctions import fetchFromSubscriberConfigTable, publishToSns

logger = logging.getLogger()
logger.setLevel(logging.INFO)

'''
Input:
{
    'Action': 'CreateVpc',
    'VpcId': record['responseElements']['vpc']['vpcId'],
    'VpcCidr': record['responseElements']['vpc']['cidrBlock'],
    'Region': aws_region
    'Rebalance': False
}

Ouput:
{
        'Action'                    : 'FetchVpnServerDetails',
        'VpcId'                             : 'vpc-xxxxxxx',
        'VpcCidr'                           : 'v.w.x.y/z',
    'Region'                    : event['Region'],
    'SubscriberAssumeRoleArn'   : '<IamRoleArn>',
    'SubscriberSnsArn'           : '<SnsTopiArn>',
        'Rebalance'                         : 'False'
}
'''
subscribingVpcTag="subscribingVpc"

subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
    
def updateDynamoDb(tableName,vpcId,vpcCidr,awsRegion):
    """Updates SubscriberLocalDb with VpcId, VpcCidr and Region
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        item={'VpcId':vpcId,'VpcCidr':vpcCidr, 'Region':awsRegion}
        table.put_item(Item=item)
        logger.info("Updated Subscriber local DynmodDB with vpc-id: {} and vpc-cidr: {}".format(vpcId,vpcCidr))
    except Exception as e:
        logger.error("Error from updateDynamoDb(), {}".format(str(e)))
 
def updateTags(awsRegion, vpcId, oldVpc):
    """Updates VPC tags with VPN-Failed keys
    """
    try:
        #Update VPC tags with
        #Key                            Value
        #ConfigStatus           Vpn-Failed
        #ConfigReason           VPC-CIDR Conflicts
        ec2Connection=boto3.client('ec2',region_name=awsRegion)
        configReason = 'Vpc-CIDR Conflicts with '+oldVpc['VpcId']+':'+oldVpc['Region']
        tags=[
            {'Key': 'ConfigStatus','Value': 'Vpn-Failed'},
            {'Key': 'ConfigReason','Value': configReason}
        ]
        ec2Connection.create_tags(Resources=[vpcId],Tags=tags)
        logger.info("Successfully Updated VPC-Failed tags to VPCID: {}".format(vpcId))
        sys.exit(0)
    except Exception as e:
        logger.info("Updating VPC-Failed tags failed, Error: {}".format(str(e)))
        sys.exit(0)

def lambda_handler(event,context):
    logger.info(event)
    try:
        subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
        if subscriberConfig:
            transitSnsTopicArn=os.environ['transitSnsTopicArn']
            transitAssumeRoleArn=os.environ['transitAssumeRoleArn']
            #Update DynamoDB table
            updateDynamoDb(subscriberConfig['SubscriberLocalDb'],event['VpcId'],event['VpcCidr'], event['Region'])
            event['SubscriberSnsArn']=subscriberConfig['SubscriberSnsArn']
            event['Rebalance']='False'
            event['SubscriberAssumeRoleArn']=subscriberConfig['SubscriberAssumeRoleArn']
            event['Action']="FetchVpnServerDetails"
            logger.info("Publishing to Transit-SNS Topoic {} By assuming Role {}".format(transitSnsTopicArn,transitAssumeRoleArn))
            publishToSns(transitSnsTopicArn, str(event), transitAssumeRoleArn)
        else:
            logger.error("No data received from SubscriberConfig Table, Error")
    except Exception as e:
        logger.error("createVpcLambda Error: {}".format(str(e)))
