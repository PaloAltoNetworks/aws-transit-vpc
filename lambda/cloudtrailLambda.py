import boto3
import json
import sys
import os
import gzip
import time
import logging
from commonLambdaFunctions import fetchFromSubscriberConfigTable, publishToSns


FILENAME = "/tmp/log.gz"
watchedEvents=['CreateTags','DeleteTags']
#subscriberConfigTable="SubscriberConfig"
subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
#SubscriberSnsArn="arn:aws:sns:us-east-1:961190221792:kumar-subscriber-sns"

subscribingVpcTag = 'subscribingVpc'
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def formRequiredData(vpcId,awsRegion, action, subscriberSns):
    """Formates the required Input for CreateVpnConnnectionLambda and DeleteVpnConnectionLambda funtions
    """
    try:
        if action=='CreateTags':
            ec2_conn = boto3.client('ec2',region_name=awsRegion)
            vpcData = ec2_conn.describe_vpcs(VpcIds=[vpcId])['Vpcs'][0]
            data = {
                'Action': 'CreateVpnConnection',
                'VpcId': vpcId,
                'VpcCidr': vpcData['CidrBlock'],
                'Region': awsRegion,
                'Rebalance': 'False'
            }
        elif action=='DeleteTags':
            data = {
                'Action': 'DeleteVpnConnection',
                'VpcId': vpcId,
                'Region': awsRegion,
                'Rebalance': 'False'
            }

        logger.info("Publishing to Subscriber-SNSTopoic: {} with Data: {}".format(subscriberSns,data))
        publishToSns(subscriberSns, str(data))
    except Exception as e:
        logger.error("Error from formRequiredData(),and exiting the process, Error: {}".format(str(e)))
        sys.exit(0)

def parse_log(path):
    with gzip.open(path, "rb") as f:
        d = json.loads(f.read().decode("utf-8"))
        try:
            subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
            if subscriberConfig:
                for record in d['Records']:
                    if record['eventName'] in watchedEvents:
                        logger.info("Record: {}".format(record))
                        if 'errorCode' not in record:
                            if record['eventName']=='CreateTags':
                                items = record['requestParameters']['resourcesSet']['items']
                                for item in items:
                                    if item['resourceId'].startswith('vpc'):
                                        tagSet = record['requestParameters']['tagSet']['items']
                                        for tag in tagSet:
                                            if tag['key']==subscribingVpcTag: 
                                                if tag['value'].lower()=='yes':
                                                    formRequiredData(item['resourceId'], record['awsRegion'], record['eventName'], subscriberConfig['SubscriberSnsArn'])
                                                #else:
                                                #    formRequiredData(item['resourceId'], record['awsRegion'], 'DeleteTags', subscriberConfig['SubscriberSnsArn'])
                            elif record['eventName']=='DeleteTags':
                                items = record['requestParameters']['resourcesSet']['items']
                                for item in items:
                                    if item['resourceId'].startswith('vpc'):
                                        tagSet = record['requestParameters']['tagSet']['items']
                                        for tag in tagSet:
                                            if tag['key']==subscribingVpcTag:
                                                if tag['value'].lower()=='yes':
                                                    formRequiredData(item['resourceId'], record['awsRegion'], record['eventName'], subscriberConfig['SubscriberSnsArn'])
                        else:
                            logger.info("Attempted to Create/DeleteTags but failed bucause of : {}".format(record['errorMessage']))
                            sys.exit(0)
            else:
                logger.error("No data received from SubscriberConfig Table, Error")
                sys.exit(0)
        except Exception as e:
            logger.info("Error from parse_log(), {}".format(str(e)))
            sys.exit(0)
def lambda_handler(event, context):
    #print(event)
    for r in event['Records']:
        bucket = r['s3']['bucket']['name']
        key = r['s3']['object']['key']
        s3 = boto3.resource('s3')
        s3_object = s3.Object(bucket, key)
        
        s3_object.download_file(FILENAME)
        parse_log(FILENAME)
        os.remove(FILENAME)
