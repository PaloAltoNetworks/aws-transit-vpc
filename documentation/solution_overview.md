# Transit VPC with VM-Series Overview

## About
This solution automates the Transit VPC solution with VM-Series. In the Transit VPC solution with VM-Series there are two VPCs.
 1. A HUB VPC where Palo Alto Firewall VM-Series firewalls will be deployed.
 2. One or more Spoke VPCs located in one or more AWS accounts, where workloads are deployed.

All Subscriber VPCs are connected to the firewalls located in the Transit VPC via IPsec tunnel. All Subscriber VPCs can talk to each other by transiting over the VM-Series located in Transit VPC when you enable route propagation on the AWS Subscriber private route table. For redundancy, the VM-Series firewalls will be located in a different availability zone.

## Architecture Diagram
![alt text](images/detailed-flowchart.png "Architecture Diagram")

## How VPN configuration is triggered
It is triggered when you add the tag "subscribingVpc=YES/Yes/yes" to an AWS VPC

## How VPN deletion is triggered
It is triggered when you change/delete the tag "subscribingVpc" tag from an AWS VPC

## Design Considerations

1. For redundancy, there should be two VM-Series firewalls establishing VPN with each VPC. Each VM-Series firewall should be in separate availability zones.

2. Each PA Group (acts as a single logical unit and has two nodes in two az's for redundancy) has a limit on maximum number of VPCs (X) it can establish a VPN with. When number of VPC exceeds the maximum limit that can be supported by existing number of PA Groups, a new PA Group should be created.

3. When a new Subscriber VPC is created, it should automatically get associated with a PA group which has capacity.

4. When new PA Groups are created to support new VPCs, each node of the newly created PA Group should establish BGP peer with nodes associated with other PA groups which belong to the same AZ.

5. To avoid Subscribing VPC traffic passing through both the VPN tunnels asymmetrically (tunnel to Node1 and Node2 of the PA group it is associated with), BGP configuration on one of the VM-Series should have an MED value set that is different from the other. To satisfy this requirement, node1 of all PA group will be using "active" bgp peer group and node2 will be using "passive" bgp peer group. The difference between these peer groups is that "passive" peer group has an MED value set and "active" does not.

6. Minimum steps are needed to setup this system.

7. Un-Subscribing from the Transit VPC should be automatic.

8. The Transit VPC should not spin up new PA (or PA Group) if the existing system has the capacity to host a new VPC.

9. When configuring AWS VPN, AWS allocates /30 ip ranges for each tunnel associated with a VPN GW. There could be conflict if subscribers are from different region or from different AWS accounts. No Overlapping subnets are allowed. 

10. To avoid conflict, each VM-Series should have a unique ASN

11. To avoid conflict, each VGW associated with a subscribing VPC should have a unique ASN

## Design Overview
This system can be split into three logical pieces
1. Task and Action
2. Transit system
3. Subscriber system

### Task and Action
Task is a JSON object exchanged between the Transit VPC and Subscriber VPC, or between states within a system. The Task has information about the next operation (Action) to be performed, and the data needed to perform the next operation. One or lambda functions associated with the State machine will execute the "Action" defined by the "Task"

eg:
{
    'Action': 'ConfigureSubscribingVpcVpn',  # Next action to perform
    'IpSegment': "169.254.8.0/28",           # Supernet of all /30s for a PA Group
    'N1T1': "169.254.8.0/30",                # /30 ip range for Node1 IPSec Tunnel 1
    'N1T2': "169.254.8.4/30",                # /30 ip range for Node1 IPSec Tunnel 2
    'N1Eip': "<Node1 EIP>",
    'N1Asn': "<Node1 BGP ASN>",
    'N2T1': "169.254.8.8/30",                # /30 ip range for Node2 IPSec Tunnel 1
    'N2T2': "169.254.8.12/30",               # /30 ip range for Node2 IPSec Tunnel 2
    'N2Eip': "<Node2 EIP>"'
    'N2Asn': "<Node2 BGP ASN>",
    'PaGroupName': "<PA Group Name>",
    'Rebalance' : "False",
    'VpcId': "<Subscriber VPC ID>",
    'VpcCidr': "<Subscriber VPC CIDR>",
    'Region': "<Subscriber VPC AWS Region>",
    'TransitVpnBucketName': "<Bucket to push VPN configuration file>",
    'TransitAssumeRoleArn': "<IAM Role to assume while contacting Transit system>",
    'TransitSnsArn': "<Transit SNS ARN>"
}

### Transit system
This logical system takes care of automatically configuring VPN and managing resources on the "Transit VPC". The Following are a few tasks handled by the transit system
- PA Group deployment
- Configuring bgp peering between PA Groups
- Providing unique ASN to the Subscriber for creating the VGW
- Providing PA Group information (Node1 and Node2 ip) for CGW creation
- Providing unique IP Pool for AWS IPSec vpn configuration
- Configurung the IPSec VPN with the Subscriber VPC
- Deleting the VPN with the Subscriber VPC


#### Components of transit system
1. Transit SNS
2. Transit Task Handler (Transit decider) (lambda)
3. BgpTunnelPool (DynamoDB Table)
4. PgGroupInfo (DynamoDB Table)
5. TransitConfig (DynamoDB Table)
6. VgwAsn (DynamoDB Table)
7. VpcTable (DynamoDB Table)
8. HighPriorityQueue(or DeleteQueue)
9. LowPriorityQueue(or CreateQueue)
10. Transit State machine (AWS Stepfunction)

##### Transit SNS
Transit SNS is a Simple Notification Service created as a part of Transit VPC setup. The Subscriber VPC communicates with the Transit VPC by sending notifications to Transit SNS. It is also connected to TransitDecider Lambda, so any new notifications will trigger TransitDecider Lambda

##### Transit Task Handler / TransitDecider
TransitDecider lambda gets invoked whenever there is a new Task pushed to the Transit SNS. It takes the task, parses the content and pushes it to the HighPriorityQueue or LowPriorityQueue. It handles all delete actions and all actions related to rebalancing (Task definition has key "Rebalance = True", indicating that task is related to Rebalance operation)

##### BgpTunnelPool (DynamoDB Table)
| IpSegment       | Available | N1T1            |  N1T2           | N2T1            | N2T2            |
|-----------------|-----------|-----------------|-----------------|-----------------|-----------------|
| 169.254.6.0/28  | Yes       | 169.254.6.0/30  | 169.254.6.4/30  | 169.254.6.8/30  | 169.254.6.12/30 |
| 169.254.6.16/28 | Yes       | 169.254.6.20/30 | 169.254.6.24/30 | 169.254.6.28/30 | 169.254.6.32/30 |


##### PgGroupInfo (DynamoDB Table)
| PaGroupName | InUse | N1Asn  |  N2Asn | VpcCount |
|-------------|-------|--------|--------|----------|
| PaGroup1    | Yes   | 64827  | 64828  | 0        |

##### TransitConfig (DynamoDB Table)
| Property                         | Value
|----------------------------------|----------------------------------------------------------------------------------|
| TransitVpcTrustedSecurityGroupId | sg-xxxxxxx                                                                       |
| UserName                         | admin                                                                            |
| PaGroupMaxVpc                    | 4                                                                                |
| TransitAssumeRoleName            | TransitAssumeRole-xxxx                                                           |
| TransitVpcTrustedSecurityGroupId | sg-xxxxxxx                                                                       |
| PaGroupInstanceProfileName       | init-transit-ac-paGroupInstanceProfile-hsfajfdak                                 |
| DeLicenseApiKey                  | HelloWorld                                                                       |
| Password                         | password                                                                         |
| TransitConfig                    | TransitConfig-hjgf                                                               |
| TransitVgwAsn                    | VgwAsn-init-transit-ac                                                           |
| TransitVpcDmzAz1SubnetGateway    | 10.100.0.1                                                                       |
| TransitVpnBucketName             | pa-transit-vpn-configuration-bucket                                              |
| TransitVpcTable                  | VpcTable                                                                         |
| SshKeyName                       | palo-alto-ssh-key                                                                |
| TransitSnsArn                    | arn:aws:sns:us-east-1:123456789:17KC0HO1YE7SN                                    |
| TransitPaGroupInfo               | PaGroupInfo-init-transit-ac                                                      |
| PaBootstrapBucketName            | pa-bootstrap-bucket                                                              |
| TransitVpcDmzAz2SubnetGateway    | 10.100.0.122                                                                     |
| PaBootstrapBucketAccessRole      | paBootstrapBucketAccessRole-17KC0HO1YE7SN                                        |
| PaGroupTemplateUrl               | https://s3.amazonaws.com/pacft/transit_pa_group.json                             |
| TransitBgpTunnelIpPool           | BgpTunnelIpPool                                                                  |
| SubscriberAccounts               | 987654321                                                                        |
| TransitVpcDmzAz1SubnetId         | subnet-xxxxxxx                                                                   |
| TransitVpcDmzAz2SubnetId         | subnet-xxxxxxy                                                                   |
| TransitVpcMgmtAz1SubnetId        | subnet-xxxxxxz                                                                   |
| LambdaCodeBucketName             | kumar-cloudtrail-bucket                                                          |
| Region                           | us-east-1                                                                        |
| TransitStateMachineArn           | arn:aws:states:us-east-1:123456789:stateMachine:TransitStateMachine-uAni8eqObjI2 |
| ServiceToken                     | arn:aws:lambda:us-east-1:123456789:function:TransitInitializeLambda-5UNZJCAZX05  |
| TransitVpcMgmtAz2SubnetId        | subnet-xxxxxyz                                                                   |
| TransitPriorityQueue             | https://sqs.us-east-1.amazonaws.com/123456789/PriorityQueue.fifo                 |
| TransitAssumeRoleArn             | arn:aws:iam::123456789:role/TransitAssumeRole                                    |
| TransitNormalQueue               | https://sqs.us-east-1.amazonaws.com/123456789/NormalQueue.fifo                   |


##### VgwAsn (DynamoDB Table)
| VgwAsn | InUse | VpcId       | VpcCidr    |
|--------|-------|-------------|------------|
| 64076  | Yes   | vpc-xxxxxxx | 10.x.x.x/x |

##### VpcTable (DynamoDB Table)
| VpcId       |	VpcCidr    | PaGroupName |	Node1VpnId | Node2VpnId  | SubscriberAssumeRoleArn  | SubscriberSnsArn         | CurrentStatus |	IpSegment |
|-------------|------------|-------------|-------------|-------------|--------------------------|--------------------------|---------------|------------|
| vpc-xxxxxxx | 10.x.x.x/x | paGroup1    | vpn-xxxxxxx | vpn-xxxxxxy | arn:iam:987654321:iamarn | arn:sns:987654321:snsarn | InProgress    | 10.x.x.x/x |


##### HighPriorityQueue(or DeleteQueue)
This is a FIFO Queue created during initialization of the Transit VPC. All new "Delete tasks" and tasks related to Rebalancing will be pushed to this queue. All tasks in this queue will be processed before processing other tasks.

##### LowPriorityQueue(or CreateQueue)
This is a FIFO Queue created during initialization of the Transit VPC. All new "Create tasks" which are not related to Rebalancing will be pushed to this task. All tasks in this queue will be processed after the high priority queue is empty and after completion of the Rebalance operation if it is in progress.

##### Transit State machine (AWS Stepfunction)
The Transit State machine is built using AWS Step functions. The Transit State machine will be started by TransitDeciderLambda and makes sure that only one instance of Transit State machine is running at all times. Once started, it fetches one task at a time from the HighPriorityQueue and processes them until the queue is empty. Once the HighPriorityQueue is empty, it checks whether the Rebalance function is in progress. It performs this by checking for a key-value pair in the DynamoDB table which indicates whether Rebalancing is in progress, or not in progress (Rebalance = Yes).

### Subscriber system
This logical system takes care of automatically configuring the VPN at the "Subscriber" VPC. The following are few tasks done by Subscriber system
- Detect VPC creation
- Gather information needed to configure VPN with PA group
- Create VGW, CGW, IPSec VPN configuration
- Notify the transit VPC with VPN configuration information so that Transit VPC can complete VPN configuration
- Detect VPN delete operation and trigger VPN delete operation from Transit system


#### Components of Subscriber system
1. Subscriber SNS
2. CloudTrail and CloudTrailLambda
3. SubscriberDecider Lambda
4. SubscriberVpcVpnTable
5. SubscriberLocalDb
6. SubscriberConfig
7. SubscriberQueue
8. Subscriber State machine

##### Subscriber SNS
The Subscriber SNS is an SNS created as part of the Subscriber VPC setup. The Transit VPC communicates with the Subscriber VPC by sending notifications to SubscriberSns. It is also connected to SubscriberDecider Lambda, so any new notifications will trigger SubscriberDecider Lambda

##### CloudTrail and CloudTrailLambda
CloudTrail logging will be enabled and configured to push logs to a new S3 bucket during the setup of Subscriber VPC. CloudTrail pushes logs to the configured bucket every 5 minutes or so. The Cloudtrail bucket is configured to trigger CloudTrailLambda which parses the latest log file and looks for any new "VPC Create" event. When it finds a new VPC Create evet, it creates a new Task and pushes that task to Subscriber SNS with action "DetectedCreateVpc" along with details about the VPC (VPC-ID, VPC-CIDR, etc.).

CloudTrailLambda can also detect VPN delete operations and if the delete VPN was configured by the solution, it activates a chain of events by creating a Task in the Transit System which eventually removes the VPN pair from the PA Group as well as Subscribing AWS Account.

NOTE 1: CloudTrail lambda can be easily modified to invoke configure vpn Tasks based on a "Create Tag" event as well.

NOTE 2: Every VPC will be connected to each VM-Series in the PA group using IPSec VPN. This two IPSec VPN configuration (to Node1, Node2 of PA Group associated with that VPC) is considered as single logical VPN connection to the transit system. Due to this, any detection of a VPN delete operation at Subscriber VPC will trigger both VPN configurations to be deleted. 

##### SubscriberDecider Lambda
SubscriberDecider lambda gets invoked whenever there is a new Task pushed on to Subscriber SNS. It takes the task and pushes it into SubscriberQueue and starts Subscriber state machine if it is not running.

##### SubscriberVpcVpnTable (DynamoDB Table)
| VpnId       | VpcId       | PaGroup    | PaNode  |
|-------------|-------------|------------|---------|
| vpn-xxxxxxx | vpc-xxxxxxx | PaGroup1   | N1      |
| vpn-xxxxxxy | vpc-xxxxxxx | PaGroup1   | N2      |

##### SubscriberLocalDb (DynamoDB Table)
| VpcId       | VpcCidr     | VgwId       | VgwAsn | PaGroup  | CgwN1       | CgwN2       | VpnN1       | VpnN2       |
|-------------|-------------|-------------|--------|----------|-------------|-------------|-------------|-------------|
| vpc-xxxxxxx | 10.x.x.x./x | vgw-xxxxxxx | 64827  | PaGroup1 | cgw-xxxxxxx | cgw-xxxxxxy | vpn-xxxxxxx | vpn-xxxxxxy |

##### SubscriberConfig (DynamoDB Table)
| Property                  | Value                                                                         |
|---------------------------|-------------------------------------------------------------------------------|
| TransitSNSTopicArn        | arn:aws:sns:us-east-1:12345667489:transitSns-arn                              |
| SubscriberAssumeRoleArn   | arn:aws:iam::987654321:role/SubscriberAssumeRole-arn                          |
| SubscriberQueueUrl        | https://sqs.us-east-1.amazonaws.com/987654321/subscriberFifoQueue.fifo        |
| SubscriberStateMachineArn | arn:aws:states:us-east-1:987654321:stateMachine:SubscrierStateMachine-Lafhjdu |
| SubscriberSnsArn          | arn:aws:sns:us-east-1:987654321:subscriberSnsTopic                            |
| SubscriberLocalDb         | SubscriberLocalDb                                                             |
| SubscriberVpcVpnTable     | SubscriberVpcVpnTable                                                         |
| SubscriberConfig          | SubscriberConfig                                                              |
| ServiceToken              | arn:aws:lambda:us-east-1:987654321:function:initializeDynamo                  |
| TransitAssumeRoleArn      | arn:aws:iam::12345667489:role/TransitAssumeRole                               |

##### SubscriberQueue (DynamoDB Table)
This is a FIFO Queue created during initialization of the Subscriber VPC. New tasks that need to be handled by the Subscriber State machine should be pushed to this Queue.

##### Subscriber State machine
The Subscriber State machine is built using AWS Step functions. The Subscriber State machine will be started by SubscriberDeciderLambda and makes sure that only one instance of the Subscriber State machine is running at all times. Once started, it fetches one Task at a time from SubscriberQueue and processes it until the Queue is empty. This is done by executing "FetchFromSubscriberQueueLambda". Based on the 'Action',  it will trigger that specific action related Lambda Function (ie., CreateVpc, ConfigureSubscribingVpcVpn,VpnConfigured etc.,). The following are the list of Tasks handled by Subscriber State machine and corresponding lambda function which gets invoked.

| Action                      | Lambda                           |
|-----------------------------|----------------------------------|
| DetectedCreateVpc           | CreateVpcLambda                  |
| ConfigureSubscribingVpcVpn  | ConfigureSubscribingVpcVpnLambda |
| VpnConfigured               | VpnConfiguredLambda              |
| VpnFailed                   | VpnFailedLambda                  |
| DetectedDeleteVpnConnection | DeleteVpnConnectionLambda        |
| DeleteVpnConnection         | <This is probably deleted?>      |
**Review Above Table**

NOTE: Details about what these lambda function does can be found in file [LambdaFunction Description](https://github.com/PaloAltoNetworks/aws-transit-vpc/blob/master/documentation/lambdafunctions-description.md)

### Rebalance mechanism

Rebalancing is basically adjusting the PaGroups based on capacity, and available VPCs.
In the Rebalance mechanism, we move VPN connections from one PaGroup(lowest capacity) to the other PaGroup(near highest capacity), so that we can remove the unused PaGroups hence reduce the cost.
The Rebalance mechanism can be triggered maually by running the initializeRebalanaceLambda function or as a cron job

- When Rebalance is in progress no other create operations get precedence, Rebalance operations will be pushed to the delete queue (HighPriorityQueue) based on the "Rebalance" key in the json event, if Rebalance==True it will send to the delete queue and gets a higher priority over Create operations
- RebalancePaGropusLambda function is the heart of the Rebalance Mechanism, it performs the rebalance functionality based on the "RebalanceInProgress" and "RebalanceStatus" values present in the TransitCongfig table, these two values are put into the TransitConfig table by initializeRebalanceLambda function
- The logic is explained as below

```
If Config.RebalanceStatus is Done:
    "Previous rebalance completed successfully or Running for the first time"
    from_to =  panGeneric.Rebalance()
    if not from_to:
        # Set config.rebalance to False
        # Rebalance completed
        exit
    # now we have a from_to to work on and move VPC
    vpcInfo = getVpcInfo(from_to["FromPaGroup"])
    config.rebalance_status = {
       "FromPaGroup": from_to["FromPaGroup"]['PaGroupName'],
       "ToPaGroupName" : from_to["ToPaGroup"]['PaGroupName'],
       "VpcId":"vpcInfo['VpcId']"
       "CreateStatus" : "Pending"
       "DeleteStatus" : "InProgress"
    }
    create DeleteVpn task and send to SSns
    Exit
        
             
else:
    "here implies rebalance in progress and Create / Delete in progress"
    previousTaskStatus = Config.RebalanceStatus
    if previousTaskStatus.DeleteStatus == "InProgress":
        "Previous task was delete task"
        "Now Check whether delete has completed"
        status = checkVpcTableForEntry(previousTaskStatus.VpcId)
        if status is not None:
            "Previous delete operation didn't complete, so skip and exit"
            exit
        else:
           "Previous delete operation completed, so create, create-task"
            config.rebalance_status['CreateStatus'] = "InProgress"
            config.rebalance_status['DeleteStatus'] = "Completed"
            Update Config table
            create CreateVpnTask and send to SSns
            and Exit
    elif previousTaskStatus.CreateStatus == "InProgress":
            "Previous task was create task"
            "Now check whether create task completed"
            status = checkVpcTableForEntry(previousTaskStatus.VpcId)
            if status is None:
                "Previous create operation didn't complete"
                "Exit and wait for that to complete"
                Exit
            Else
                "Now we found an entry on VPC table lets check whether it the configuration we expect"
                if status.PaGroupName == config.rebalance_status.ToPaGroupName:
                    "If they are same, it means configuration is completed and accurate"
                    config.rebalance_status = None
                    Return to Transit task handler (to continue rebalance operation)
                Else:
                    Something terrible happened? Unknown status
                    Print error and exit

```
