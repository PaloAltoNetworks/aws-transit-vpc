import boto3
import sys, os
import json
import logging
from commonLambdaFunctions import fetchFromTransitConfigTable, fetchFromQueue

logger = logging.getLogger()
logger.setLevel(logging.INFO)

transitConfigTable = os.environ['transitConfigTable']

#transitConfigTable='TransitConfig'
def lambda_handler(event,context):
    try:
        transitConfig=fetchFromTransitConfigTable(transitConfigTable)
        if transitConfig:
            if 'StackError' not in transitConfig:
                logger.info("Reading from Priority Queue")
                receive_message=fetchFromQueue(transitConfig['TransitPriorityQueue'])
                logger.info("Message from Priority Queue is: {}".format(receive_message))
                if receive_message:
                    for message in receive_message['Messages']:
                        action=message['Body']
                        action=json.loads(action.replace('\'','\"'))
                        return action
                logger.info("Checking ReabalanceInProgress or not")
                if 'RebalanceInProgress' in transitConfig:
                    if transitConfig['RebalanceInProgress']=='True':
                        logger.info("YES, ReabalanceInProgress")
                        action = {'Action':'RebalancePaGroups'}
                        return action
                logger.info("NO, ReabalanceInProgress")
                logger.info("Reading from Normal Queue")
                receive_message=fetchFromQueue(transitConfig['TransitNormalQueue'])
                logger.info("Message from Normal Queue is: {}".format(receive_message))
                if receive_message:
                    for message in receive_message['Messages']:
                        action=message['Body']
                        action=json.loads(action.replace('\'','\"'))
                        return action
            else:
                logger.error("PA Group Stack Creation Failed, {}".format(transitConfig['StackError']))
                sys.exit(0)
        else:
            logger.error("Not Received any data from TransitConfig table")
            sys.exit(0)
    except Exception as e:
        logger.error("Error: {}".format(str(e)))
        sys.exit(0)
