import boto3
import logging, os

'''
Input:
{
	'Action': 'VpnFailed',
	'VpcId': 'vpc-xxxxxxxx',
	'Region': '<awsRegion>'
}
'''

logger = logging.getLogger()
logger.setLevel(logging.INFO)

subscriberLocalDb = os.environ['subscriberLocalDb']
region = os.environ['Region']

def deleteItemFromLocalDb(vpcId):
    """Deletes item from SubscirberLocalDb by specifying the VpcId primary key
    """
    try:
        dynamodb = boto3.resource('dynamodb',region_name=region)
        table = dynamodb.Table(subscriberLocalDb)
        table.delete_item(
            Key={'VpcId':vpcId}
        )
        logger.info("Successfully Deleted {} entry from LocalDb".format(vpcId))
    except Exception as e:
        logger.info("Deletion of {} entry from LocalDb failed, Error: {}".format(vpcId,str(e)))
		
def lambda_handler(event,context):
    try:
        #Delete entry from LocalDb 
        deleteItemFromLocalDb(event['VpcId'])
        #Update VPC tags with
        #Key				Value
        #ConfigStatus 		Vpn-Failed
        #ConfigReason 		VPC-CIDR Conflicts
        ec2Connection=boto3.client('ec2',region_name=event['Region'])
        tags=[
            {'Key': 'ConfigStatus','Value': 'Vpn-Failed'},
            {'Key': 'ConfigReason','Value': 'VPC-CIDR Conflicts'}
        ]
        ec2Connection.create_tags(Resources=[event['VpcId']],Tags=tags)
        logger.info("Updated VPC-Failed tags to VPCID: {}".format(event['VpcId']))
    except Exception as e:
        logger.info("Updating VPC-Failed tags failed, Error: {}".format(str(e)))
