# Palo Alto Bootstrapping
Bootstrapping the Palo Alto server ensures that it spins up with all the required initial configurations. This document talks about how to prepare Palo Alto bootstrap configuration file needed for this solution

## Configurations
Below are the steps to make the required initial configurations, that would later be used during Initialization and Post Configuration to achieve the complete setup:

### Admin Password
To optionally change the default admin password, perform the following steps:

1. Navigate to **Device** > **Administrators** > **admin**.

2. Then, enter the old password, new password and confirm the new password.

3. Then, click on "Ok".

### Dataplane interface address objects
Create a dummy address object, to be assigned to the eth1/1 interface which is the Dataplane interface for this setup. During initialization, this address object will be updated to the actual interface IP.

1. Navigate to **Objects** > **Addresses** > **Add**.

2. Enter a name for the object (here, **eth1**).

3. Optionally enter a description.

4. For the Type "IP Netmask", enter a dummy IP address (here, 172.15.15.15).

5. Then, click "Ok".

### Management Profile for the DataPlane Interface
Create a Dataplane interface management profile to enable the services to be allowed on this interface.

1. Navigate to **Network** > **Interface Mgmt** > **Add**.

2. Enter a descriptive name for the profile (here, **DataPlane**).

3. Check against all the permitted services to enable them.

4. Then click "Ok".

### Dataplane interface
Create an Ethernet layer3 interface (ethernet1/1) and attach the dummy address object (eth1), created previously as the IP address for this interface. Also attach the pre-created interface Management Profile, set a Zone (here, UNTRUST) and associate the interface to the Default Virtual Router.

1. Navigate to **Network** > **Interfaces** > **ethernet1/1**.

2. Optionally, enter a comment.

3. From the interface dropdown, select "Layer3".

4. Click on the "Config" tab, and from the Virtual Router dropdown, select **default**.

5. Click on the Security Zone dropdown, select "New Zone". Enter a descriptive name for the Zone (here, **UNTRSUT**) and under Interfaces, add the previously created "ethernet1/1" interface. Then, click on "Ok".

6. Now, click on the "IPv4" tab, and select tab as "Static". Under "IP", click on Add and select the "eth1" address object.

7. Then, click on the "Advanced" tab, under Other Info > Management Profile, select the "DataPlane" profile from the dropdown.

8. Click on Ok.

### Default Static Route for the ethernet1/1 interface
Create a default static route for the eth1/1 interface, with destination 0.0.0.0/0 and next hop set to a dummy IP address. During initialization, the interface subnet gateway IP address will be fetched from AWS and the destination entry in this static route will be modified.

1. Navigate to **Network** > **Virtual Routers** > **Default** > **Static Routes** > **IPv4** > **Add**.

2. Enter a descriptive name for the static route.

3. For Destination, enter "0.0.0.0/0".

4. From the Interface dropdown, select "ethernet1/1".

5. From the Next Hop dropdown, select "IP Address". Enter a dummy IP address for in the dialog box (here, "1.1.1.1").

6. Then, click on "Ok".

### BGP Settings

#### General Settings
Edit the BGP settings on the default Virtual Router to enable BGP, enable install-route, set Router ID (dummy IP) and a dummy BGP ASN. During initialization, the Public IP address, BGP ASN associated with the ethernet1/1 interface (CGW definitions on AWS VPC) will be fetched and the Palo Alto BGP settings will be modified accordingly.

1. Navigate to **Network** > **Virtual Routers** > **Default** > **BGP**.

2. Check against the Enable box to enable BGP.

3. Enter a dummy IP in the Router ID dialog box (here, "1.2.3.4").

4. Enter a dummy local ASN in the AS Number dialog box (here, "65065").

5. Under **General** > **Options**, check against the Install Route box.

6. Then, click on "Ok".

#### BGP Peer Groups
Add two empty BGP peer groups (here, Active and Passive). Depending on the role of the PA server, peers will be added to the Active/ Passive BGP Peer Group.

1. Navigate to **Network** > **Virtual Routers** > **Default** > **BGP** > **Peer Group** > **Add**.

2. Enter a name for the peer group, (here, **Active**), check against the "Enable" box and click on "Ok".

3. Create and enable a second BGP peer group and name it **Passive**.

4. Then click on "Ok".

#### Route Preference using MED
Create a BGP Export rule to be used by the Passive peer, set action to allow and MED to 10. This step ensures that the Active Palo Alto server is preferred over the Passive one.

1.  Navigate to **Network** > **Virtual Routers** > **Default** > **BGP** > **Export** > **Add**.

2. Under the General tab, in the Rules dialog box, enter a descriptive name for the Export rule (here, **BGPExport**).

3. Under Used By, click on Add, and select the **Passive** Peer Group.

4. Under the Actions tab, click on the Actions dropdown and select Allow.

5. In the MED dialog box, enter "10".

6. Then click on "Ok".

### IKE and IPSec Crypto Profiles
AWS use standard IKE and IPSec Crypto profiles for all its VPNs. Create standard IKE and IPSec Crypto Profiles for all the subsequent AWS VPN connections.

#### IKE Crypto Profile
1. Navigate to **Network** > **IKE Crypto** > **Add**.

2. Enter a name for the IKE Crypto profile (here, **aws-ike-crypto**).

3. Under DH Group, click on Add, and from the dropdown, select "group2".

4. Under Authentication, click on Add, and from the dropdown, select "sha1".

5. Under Encryption, click on Add, and from the dropdown, select "aes-128-cbc".

6. Under Timers, from the Key Lifetime dropdown, select "seconds" and in the dialog box, enter "28800".

7. Then, click on "Ok".

#### IPSec Crypto Profile
1. Navigate to **Network** > **IPSec Crypto** > **Add**.

2. Enter a name for the IPSec Crypto profile (here, **aws-ipsec-crypto**).

3. From the IPSec protocol dropdown, select "ESP".

4. Under Encryption, click on Add, and from the dropdown, select "aes-128-cbc".

5. Under Authentication, click on Add, and from the dropdown, select "sha1".

6. From the DH Group dropdown, select "group2".

7. From the Lifetime dropdown, select "Seconds" and in the dialog box, enter "3600". Then click on "Ok".

Then click on "Commit" to save the changes.

## Bootstrap file
After performing all the above configurations and saving the changes, extract the bootstrap.xml file.

1. Navigate to **Device** > **Setup** > **Operations** > **Configuration Management** > **Export** > **Export named configuration snapshot**.

2. From the Name dropdown, select "running-config.xml".

3. Then click on "Ok".

This should save the file to your local computer. Rename the file to "**bootstrap.xml**" and upload this file to the Palo Alto Bootstrap S3 bucket under the "config" folder.

## How to change the password of PA-VM Firewall
1. Launch one PA-VM series firewall with the above bootstrap setup
2. Login to the server with user-name: **admin** password: **ReanCloud123!**
3. Change the password for **admin** user as per your requirement
4. Navigate to **Device** > **Setup** > **Operations** > **Configuration Management** > **Export** > **Export named configuration snapshot**.
5. From the Name dropdown, select "running-config.xml".
6. Then click on "Ok".

This should save the file to your local computer. Rename the file to **bootstrap.xml** and upload this file to the Palo Alto Bootstrap S3 bucket under the "config" folder.
