import boto3
import sys
import json
import logging, os
from commonLambdaFunctions import fetchFromTransitConfigTable, sendToQueue

logger = logging.getLogger()
logger.setLevel(logging.INFO)


sfnConnection=boto3.client('stepfunctions')

normalQueue=['FetchVpnServerDetails','ConfigureSubscriberVpcVpn','ConfigureTransitVpn','SubscriberVpnConfigurationFailed']
priorityQueue=['DeleteVpc','DeleteTransitVpnConfiguration','DeletePAServerGroup','DeleteVpnConnection']
#rebalanceQueue = ['RebalancePaGroups', 'RebalanceConfigureSubscriberVpn', 'RebalanceConfigureTransitVpn']

#transitConfigTable='TransitConfig'
transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

def lambda_handler(event,context):
    try:
        transitConfig=fetchFromTransitConfigTable(transitConfigTable)
        if transitConfig:
            logger.info("Got Event {}".format(event))
            for r in event['Records']:
                sns = r['Sns']
                message = sns['Message']
                message=json.loads(message.replace('\'','\"'))
                logger.info(message)
                if message['Rebalance']=='True':
                    logger.info("Writting to PriorityQueue beacuse of Rebalance Operation")
                    sendToQueue(transitConfig['TransitPriorityQueue'],sns['Message'],message['Action'])
                elif message['Action'] in priorityQueue:
                    logger.info("Writting to PriorityQueue")
                    sendToQueue(transitConfig['TransitPriorityQueue'],sns['Message'],message['Action'])
                elif message['Action'] in normalQueue and message['Rebalance']!='True':
                    logger.info("Writting to NormalQueue")
                    sendToQueue(transitConfig['TransitNormalQueue'],sns['Message'],message['Action'])
            #Cheking for the StateMachine status
            logger.info("Checking for the StateMachine Status")
            if sfnConnection.list_executions(stateMachineArn=transitConfig['TransitStateMachineArn'],statusFilter='RUNNING')['executions']:
                logger.info("StateMachine is Running, hence exiting from execution")
                sys.exit(0)
            else:
                logger.info("StateMachine is not Running, hence starting StepFunction")
                sfnConnection.start_execution(stateMachineArn=transitConfig['TransitStateMachineArn'])
        else:
            logger.error("Not Received any data from TransitConfig table")
    except Exception as e:
        logger.error("Error from TransitDecider(), Error: {}".format(str(e)))

