import boto3
import logging
import os
from commonLambdaFunctions import fetchFromSubscriberConfigTable, sendToQueue
from boto3.dynamodb.conditions import Key, Attr
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn_conn=boto3.client('stepfunctions')
subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']

def lambda_handler(event,context):
    logger.info("Got Event {}".format(event))
    try:
        subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
        if subscriberConfig:
            for r in event['Records']:
                sns = r['Sns']
                message = sns['Message']
                message=json.loads(message.replace('\'','\"'))
                logger.info("Writting message to Subscirber Queue")
                logger.info(message)
                response = sendToQueue(subscriberConfig['SubscriberQueueUrl'],sns['Message'],message['Action'])
            #Cheking for the StateMachine status
            logger.info("Checking for the StateMachine Status")
            if sfn_conn.list_executions(stateMachineArn=subscriberConfig['SubscriberStateMachineArn'],statusFilter='RUNNING')['executions']:
                logger.info("StateMachine is Running, hence exiting from execution")
                sys.exit(0)
            else:
                logger.info("StateMachine is not Running, hence starting StepFunction")
                sfn_conn.start_execution(stateMachineArn=subscriberConfig['SubscriberStateMachineArn'])
        else:
            logger.error("No data received from SubscriberConfig Table, Error")
            return
    except Exception as e:
        logger.error(str(e))
