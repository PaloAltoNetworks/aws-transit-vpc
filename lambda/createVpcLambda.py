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
#subscriberConfigTable="SubscriberConfig"
#region = "us-east-1"

subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
    
def updateDynamoDb(tableName,vpcId,vpcCidr,awsRegion):
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(tableName)
        item={'VpcId':vpcId,'VpcCidr':vpcCidr, 'Region':awsRegion}
        table.put_item(Item=item)
        logger.info("Updated Subscriber local DynmodDB with vpc-id: {} and vpc-cidr: {}".format(vpcId,vpcCidr))
    except Exception as e:
        logger.error("Error from updateDynamoDb(), {}".format(str(e)))
def updateTags(awsRegion, vpcId):
    try:
        #ConfigReason       VPC-CIDR Conflicts
        ec2 =boto3.client('ec2',region_name=awsRegion)
        tags=[
            {
                'Key': 'ConfigStatus',
                'Value': 'Vpn-Failed'
            },
            {
                'Key': 'ConfigReason',
                'Value': 'VPC-CIDR Conflicts'
            }
        ]
        ec2.create_tags(Resources=[vpcId],Tags=tags)
        logger.info("Updated VPC-Failed tags to VPCID: {}".format(vpcId))
        sys.exit(0)
    except Exception as e:
        logger.info("Updating VPC-Failed tags failed, Error: {}".format(str(e)))

def isSubscribingVpc(id,region):
    try:
        ec2_conn = boto3.client('ec2',region_name=region)
        vpc_tags=ec2_conn.describe_tags(Filters=[{'Name':'resource-id','Values':[id]}],MaxResults=99)['Tags']
        for tag in vpc_tags:
            if tag['Key']==subscribingVpcTag:
                if tag['Value'].lower()=='yes':
                    return True
    except Exception as e:
        logger.info("Error from isSubscribingVpc(), {}".format(str(e)))

def lambda_handler(event,context):
    logger.info(event)
    try:
        subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
        if subscriberConfig:
            transitSnsTopicArn=os.environ['transitSnsTopicArn']
            transitAssumeRoleArn=os.environ['transitAssumeRoleArn']
            result=isSubscribingVpc(event['VpcId'],event['Region'])
            if result:
                #Update DynamoDB table
                updateDynamoDb(subscriberConfig['SubscriberLocalDb'],event['VpcId'],event['VpcCidr'], event['Region'])
                event['SubscriberSnsArn']=subscriberConfig['SubscriberSnsArn']
                event['Rebalance']='False'
                event['SubscriberAssumeRoleArn']=subscriberConfig['SubscriberAssumeRoleArn']
                event['Action']="FetchVpnServerDetails"
                logger.info("Publishing to Transit-SNS Topoic {} By assuming Role {}".format(transitSnsTopicArn,transitAssumeRoleArn))
                publishToSns(transitSnsTopicArn, str(event), transitAssumeRoleArn)
            else:
                logger.info("Not SubscribingVpc")
        else:
            logger.error("No data received from SubscriberConfig Table, Error")
    except Exception as e:
        logger.error("createVpcLambda Error: {}".format(str(e)))
