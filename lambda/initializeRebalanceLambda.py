import boto3
import os, sys
from boto3.dynamodb.conditions import Key,Attr
from commonLambdaFunctions import fetchFromTransitConfigTable, publishToSns
import logging

transitConfigTable = os.environ['transitConfigTable']
region = os.environ['Region']

sfnConnection=boto3.client('stepfunctions',region_name=region)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info('Got Event: {}'.format(event))
    try:
        transitConfig=fetchFromTransitConfigTable(transitConfigTable)
        #Update Transit Config with RebalanceInProgress to True
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(transitConfigTable)
        table.put_item(Item={'Property':'RebalanceInProgress', 'Value':'True'})
        table.put_item(Item={'Property':'RebalanceStatus', 'Value':'Done'})
        logger.info("Successfully updated Transit Config with RebalaneInProgress==True and RebalanceStatus=Done")
        

        logger.info("Checking for the StateMachine Status")
        if sfnConnection.list_executions(stateMachineArn=transitConfig['TransitStateMachineArn'],statusFilter='RUNNING')['executions']:
            logger.info("StateMachine is Running, hence exiting from execution")
            sys.exit(0)
        else:
            logger.info("StateMachine is not Running, hence starting StepFunction")
            sfnConnection.start_execution(stateMachineArn=transitConfig['TransitStateMachineArn'])
    except Exception as e:
        logger.error("Error from initilizationRebalance(), Error: {}".format(str(e)))
