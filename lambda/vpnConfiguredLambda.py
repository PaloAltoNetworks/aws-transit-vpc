import boto3
import logging, os
'''
Input:
{
	'Action': 'VpnConfigured',
	'VpcId': 'vpc-xxxxxxxx',
	'Region': '<awsRegion>',
    'PaGroupName': event['PaGroupName']
}
'''
logger = logging.getLogger()
logger.setLevel(logging.INFO)

subscriberLocalDb = os.environ['subscriberLocalDb']
region = os.environ['Region']
#region = "us-east-1"

def updateLocalDb(vpcId):
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(subscriberLocalDb)
        table.update_item(Key={'VpcId':vpcId},AttributeUpdates={'VpnStatus':{'Value':'Configured','Action':'PUT'}})
        logger.info("Successfully updated VpnStatus=Configured for VpcId: {} in SubscriberLocalDb".format(vpcId))
    except Exception as e:
        logger.error("Updating of VpnStatus=Configured for VpcId: {} in LocalDb failed, Error: {}".format(vpcId,str(e)))

def lambda_handler(event,context):
    try:
        updateLocalDb(event['VpcId'])
		#Update VPC tags with
		#Key				Value
		#ConfigStatus 		Vpn-Configured
		#ConfigReason 		Active
        ec2Connection=boto3.client('ec2',region_name=event['Region'])
        tags=[
            {'Key': 'ConfigStatus','Value': 'Vpn-Configured' },
            {'Key': 'ConfigReason','Value': 'Active'},
            {'Key': 'ConfiguredWith', 'Value': event['PaGroupName']}
        ]
        ec2Connection.create_tags(Resources=[event['VpcId']],Tags=tags)
        logger.info("Updated VPC-Configured tags to VPCID {}".format(event['VpcId']))
    except Exception as e:
        logger.error("Updating VPC Configure tags failed, Error: {}".format(str(e)))
