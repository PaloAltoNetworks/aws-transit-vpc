import boto3
import logging, os
import json
from commonLambdaFunctions import fetchFromQueue, fetchFromSubscriberConfigTable

logger = logging.getLogger()
logger.setLevel(logging.INFO)

'''
#Reading From Environment varialbes
subscriberQueueUrl=os.environ['subscriberQueueUrl']
'''
#subscriber_queue_url="https://sqs.us-east-1.amazonaws.com/961190221792/kumar_subscriber_queue"

#subscriberConfigTable="SubscriberConfig"
subscriberConfigTable = os.environ['subscriberConfigTable']
region = os.environ['Region']

def lambda_handler(event,context):
    logger.info("Got Event {}".format(event))
    try:
        subscriberConfig=fetchFromSubscriberConfigTable(subscriberConfigTable)
        if subscriberConfig:
            logger.info("Reading from Queue")
            receive_message=fetchFromQueue(subscriberConfig['SubscriberQueueUrl'])
            if 'Messages' in receive_message:
                for message in receive_message['Messages']:
                    action=message['Body']
                    action=json.loads(action.replace('\'','\"'))
                    return action
            else:
                event={'Action':'Null'}
                return event
        else:
            logger.error("No data received from SubscriberConfig Table, Error")
            return 
    except Exception as e:
        logger.error(str(e))
        return
