# Solution documentation

## Brief description about the solution
This solution automates baseline Firewall Services VPC solution. In baseline Firewall services VPC there are two VPCs.
 1. A HUB VPC where Palo Alto Firewall devises will be deployed
 2. One or more Spoke VPCs located in one or more AWS accounts,  where workloads are deployed

All Spoke VPCs are connected to Palo Alto Firewall located in HUB VPC. All Spoke VPCs can talk to each other by transiting over Palo Alto (PA) servers located in HUB VPC. For redundancy, there will be a pair of PA server attached to a VPC and each of the node in the pair will be located in a different availability zone.

## Design considerations
1. When a Spoke VPC or Subscribing VPC is created, it should trigger automatic configuration of VPN with a PA server pair in HUB VPC

2. For redundancy there should be two PA Servers establishing VPN with each VPC and each PA server should be in separate availability zone

3. Each PA Group (acts as a single logical unit and has two nodes in two az for redundancy) has a limit on maximum number of VPCs (X) it can establish VPN with. When number of VPC exceeds the maximum limit that can be supported by existing number of PA Groups, a new PA Group should be created

4. When a new Subscriber VPC is created, it should automatically get associated with a PA group which has capacity

5. When new PA Groups are created to support new VPCs, each node of the newly created PA Group should establish BGP peer with nodes associated with other PA groups which belong to the same AZ

6. To avoid traffic from Subscribing VPC to pass through both the VPN tunnels (tunnel to Node1 and Node2 of the PA group it is associated with), BGP configuration on one of the node should have an MED value set that is different from the other. To satisfy this requirement, node1 of all PA group will be using "active" bgp peer group and node2 will be using "passive" bgp peer group. The difference between these peer groups is that "passive" peer group has an MED value set and "active" doesn't

7. Minimum manual steps from a customer who want to setup this system

8. Un subscription from the system should be automatic

9. System shouldn't spin up new PA (or PA Group) if existing system have capacity to host new VPC

10. When configuring AWS VPN, AWS allocates /30 ip ranges for each tunnel associated with a VPN GW. There could be conflict if subscribers are from different region or from different AWS accounts.

11. To avoid conflict, each PA node should have unique ASN

12. To avoid conflict, each VGW associated with subscribing VPC should have unique ASN

## Design Overview
This system can be split into two logical pieces
1. Task  
2. Transit system
3. Subscriber system

### Task and Action
Task is a JSON object exchanged between Transit system and subscriber system or between states within a system. The Task has information about next operation (Action) to be performed and data needed to perform next operation. One or lambda function associated with State machine will execute the "Action" defined by the "Task"

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
This logical system takes care of automatically configuring VPN and managing resources on the "Transit"/"HUB" side. Following are few tasks done by transit system
- PA Group deployment
- Configuring bgp peering between PA Groups
- Providing unique ASN to Subscriber for creating VGW
- Providing PA Group information (Node1 and Node2 ip) for CGW creation
- Providing unique IP Pool for AWS IPSec vpn configuration
- Configure IPSec VPN with Subscriber VPC
- Deleting VPN with Subscriber VPC

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
Transit SNS is an SNS created as part of Transit environment setup. Subscriber system communicates with Transit system by sending notification to TransitSns. It is also connected to TransitDecider Lambda, so any new notification will trigger TransitDecider Lambda

##### Transit Task Handler / TransitDecider
TransitDecider lambda gets invoked whenever there is a new Task pushed on to Transit SNS. It takes the task, parse the content and pushes it into HighPriorityQueue or LowPriorityQueue. All delete action and all actions which are related to rebalance (Task definition has key "Rebalance = True", indicating that task is related to Rebalance operation)

##### BgpTunnelPool (DynamoDB Table)
<@Venu> Add structure of the table here

##### PgGroupInfo (DynamoDB Table)

##### TransitConfig (DynamoDB Table)

##### VgwAsn (DynamoDB Table)

##### VpcTable (DynamoDB Table)

##### HighPriorityQueue(or DeleteQueue)
This is a FIFO Queue created during initialization of Transit account. All new Delete tasks and tasks related to Rebalance will be pushed on to this queue. All tasks in this queue will be processed before processing other tasks.

##### LowPriorityQueue(or CreateQueue)
This is a FIFO Queue created during initialization of Transit account. All new create tasks which are not related to Rebalance will be pushed on to this task. All tasks in this queue will be processed after high priority queue is empty and after completion of Rebalance operation if it is in progress.

##### Transit State machine (AWS Stepfunction)
Transit State machine is built using AWS Step functions. Transit State machine will be started by TransitDeciderLambda and makes sure that only one instance of Transit State machine is running at any point in time. Once started it fetches one Task at a time from HighPriorityQueue and process them till queue is empty. Once HighPriorityQueue is empty, it checks whether Rebalance is in progress by checking for a key-value pair in DynamoDB which indicates whehter Rebalance is in progress or not (Rebalance = Yes). If there is an ongoing Rebalance, Transit





### Subscriber system
This logical system takes care of automatically configuring VPN at the "subscriber" side. Following are few tasks done by Subscriber system
- Detect VPC creation
- Gather information needed to configure VPN with PA group
- Create VGW, CGW, IPSec VPN configuration
- Notify transit system with VPN configuration information so that Transit system can complete VPN configuration
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
Subscriber SNS is an SNS created as part of Subscriber environment setup. Transit system communicates with subscruber system by sending notification to SubscriberSns. It is also connected to SubscriberDecider Lambda, so any new notification will trigger SubscriberDecider Lambda

##### CloudTrail and CloudTrailLambda
CloudTrail logging will be enabled and configured to push logs to a new S3 bucket during the setup of Subscriber environment. CloudTrail pushes logs to the configured bucket every 5 minutes or so. Cloudtrail bucket is configured to trigger CloudTrailLambda which parses latest log file and look for any new "VPC Create" event and when it finds one, it creates a new Task and push that task to Subscriber SNS with action "DetectedCreateVpc" along with details about the VPC (VPC-ID, VPC-CIDR, etc.).

CloudTrailLambda can also detect VPN delete operations and if the delete VPN was configured by the solution, it activates a chain of events by creating a Task in the Transit System which eventually removes VPN pair from PA Group as well as Subscribing AWS Account.

NOTE 1: CloudTrail lambda can be easily modified to invoke configure vpn Task based on "Create Tag" event as well

NOTE 2: Every VPC will be connected to each node associated PA-Server group using IPSec VPN. This two IPSec configuration (to Node1, Node2 of PA Group associated with that VPC) is considered as single logical VPN connection to the transit system. Due to that reason, detection of one of the VPN configuration delete operation at Subscriber VPC will trigger both VPN configurations

##### SubscriberDecider Lambda
SubscriberDecider lambda gets invoked whenever there is a new Task pushed on to Subscriber SNS. It takes the task and pushes it into SubscriberQueue and starts Subscriber state machine if it is not running.

##### SubscriberVpcVpnTable (DynamoDB Table)

##### SubscriberLocalDb (DynamoDB Table)

##### SubscriberConfig (DynamoDB Table)

##### SubscriberQueue (DynamoDB Table)
This is a FIFO Queue created during initialization of Subscriber account. New tasks that need to be handled by Subscriber State machine should be pushed on to this Queue.

##### Subscriber State machine
Subscriber State machine is built using AWS Step functions. Subscriber State machine will be started by SubscriberDeciderLambda and makes sure that only one instance of Subscriber State machine is running at any point in time. Once started it fetches one Task at a time from SubscriberQueue and process it till the Queue is empty this is done by executing "FetchFromSubscriberQueueLambda". Based on the 'Action' it will trigger that specific action related Lambda Function (ie., CreateVpc, ConfigureSubscribingVpcVpn,VpnConfigured etc.,). Following are the list of Tasks handled by Subscriber State machine and corresponding lambda function which gets invoked.

| Action                      | Lambda                           |
|-----------------------------|----------------------------------|
| DetectedCreateVpc           | CreateVpcLambda                  |
| ConfigureSubscribingVpcVpn  | ConfigureSubscribingVpcVpnLambda |
| VpnConfigured               | VpnConfiguredLambda              |
| VpnFailed                   | VpnFailedLambda                  |
| DetectedDeleteVpnConnection | DeleteVpnConnectionLambda        |
| DeleteVpnConnection         | <This is probably deleted?>      |

NOTE: Details about what these lambda function does can be found in file lambdafunctions-description.md

### Rebalance mechanism
