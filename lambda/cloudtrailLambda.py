import boto3
import json
import sys
import os
import gzip
import time
import logging
from commonLambdaFunctions import fetchFromSubscriberConfigTable, publishToSns


FILENAME = "/tmp/log.gz"
watchedEvents=['CreateVpc','DeleteVpnConnection']
#subscriberConfigTable="SubscriberConfig"
subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']
#SubscriberSnsArn="arn:aws:sns:us-east-1:961190221792:kumar-subscriber-sns"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def parse_log(path):
    with gzip.open(path, "rb") as f:
        d = json.loads(f.read().decode("utf-8"))
        try:
            subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
            if subscriberConfig:
                for record in d['Records']:
                    if record['eventName'] in watchedEvents:
                        if record['eventName']=='DeleteVpnConnection':
                            if 'errorCode' not in record:
                                data = {
                                   'Action': 'DeleteVpnConnection', 
                                   'VpnId': record['requestParameters']['vpnConnectionId'],
                                   'Region': record['awsRegion'],
                                   'Rebalance': 'False'
                                } 
                                logger.info("Publishing to Subscriber-SNSTopoic: {} with Data: {}".format(subscriberConfig['SubscriberSnsArn'],data))
                                publishToSns(subscriberConfig['SubscriberSnsArn'], str(data))
                            else:
                                logger.info("Attempted to DeleteVpnConnection but failed bucause of : {}".format(record['errorMessage']))
                                sys.exit(0)
                        elif record['eventName']=='CreateVpc':
                            data={
                                'Action': 'CreateVpc',
                                'VpcId': record['responseElements']['vpc']['vpcId'],
                                'VpcCidr': record['responseElements']['vpc']['cidrBlock'],
                                'Region': record['awsRegion'],
                                'Rebalance': 'False'
                            }
                            logger.info("Publishing to Subscriber-SNSTopoic: {} with Data: {}".format(subscriberConfig['SubscriberSnsArn'],data))
                            publishToSns(subscriberConfig['SubscriberSnsArn'], str(data))
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
