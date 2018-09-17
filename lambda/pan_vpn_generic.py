#!/usr/bin/env python3

import re
import ssl
import sys
import urllib
import xml
import boto3


class XmlListConfig(list):
    def __init__(self, aList):
        for element in aList:
            if element:
                # treat like dict
                if len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                # treat like list
                elif element[0].tag == element[1].tag:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)


class XmlDictConfig(dict):
    '''
    Example usage:

    >>> tree = ElementTree.parse('your_file.xml')
    >>> root = tree.getroot()
    >>> xmldict = XmlDictConfig(root)

    Or, if you want to use an XML string:

    >>> root = ElementTree.XML(xml_string)
    >>> xmldict = XmlDictConfig(root)

    And then use xmldict for what it is... a dict.
    '''

    def __init__(self, parent_element):
        if parent_element.items():
            self.update(dict(parent_element.items()))
        for element in parent_element:
            if element:
                # treat like dict - we assume that if the first two tags
                # in a series are different, then they are all different.
                if len(element) == 1 or element[0].tag != element[1].tag:
                    aDict = XmlDictConfig(element)
                # treat like list - we assume that if the first two tags
                # in a series are the same, then the rest are the same.
                else:
                    # here, we put the list in dictionary; the key is the
                    # tag name the list elements all share in common, and
                    # the value is the list itself
                    aDict = {element[0].tag: XmlListConfig(element)}
                # if the tag has attributes, add those to the dict
                if element.items():
                    aDict.update(dict(element.items()))
                self.update({element.tag: aDict})
            # this assumes that if you've got an attribute in a tag,
            # you won't be having any text. This may or may not be a
            # good idea -- time will tell. It works for the way we are
            # currently doing XML configuration files...
            elif element.items():
                self.update({element.tag: dict(element.items())})
            # finally, if there are no child tags and no attributes, extract
            # the text
            else:
                self.update({element.tag: element.text})


def makeApiCall(hostname, data):
    '''Function to make API call
    '''
    # Todo: 
    # Context to separate function?
    # check response for status codes and return reponse.read() if success 
    #   Else throw exception and catch it in calling function
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = "https://" + hostname + "/api"
    encoded_data = urllib.parse.urlencode(data).encode('utf-8')
    return urllib.request.urlopen(url, data=encoded_data, context=ctx).read()


def getApiKey(hostname, username, password):
    '''Generate API keys using username/password
    API Call: http(s)://hostname/api/?type=keygen&user=username&password=password
    '''
    data = {
        'type': 'keygen',
        'user': username,
        'password': password
    }
    response = makeApiCall(hostname, data)
    return xml.etree.ElementTree.XML(response)[0][0].text


def panOpCmd(hostname, api_key, cmd):
    '''Function to make an 'op' call to execute a command
    '''
    data = {
        "type": "op",
        "key": api_key,
        "cmd": cmd
    }
    return makeApiCall(hostname, data)


def panCommit(hostname, api_key, message=""):
    '''Function to commit configuration changes
    '''
    data = {
        "type": "commit",
        "key": api_key,
        "cmd": "<commit>{0}</commit>".format(message)
    }
    return makeApiCall(hostname, data)


def checkPaGroupReady(username, password, paGroup):
    '''Function to check whether a PaGroup (both Nodes N1 and N2) is ready to accept API calls
    This is done by trying to generate "API" key using username/password
    '''
    try:
        api_key_N1 = getApiKey(paGroup['N1Mgmt'], username, password)
        api_key_N2 = getApiKey(paGroup['N2Mgmt'], username, password)
        if api_key_N1 == api_key_N2:
            return True
        else:
            print("Error: API key of both nodes of the group doesn't match ")
            return False
    except:
        print("Error while retriving API Key")
        return False


# Test This
def configDeactivateLicenseApiKey(hostname, api_key, license_api_key):
    '''Function to configure DeactivateLicense API Key
    This function is used during initialization of a PA Node and requires internet connectivity
    '''
    cmd = "<request><license><api-key><set><key>" + license_api_key + "</key></set></api-key></license></request>"
    return panOpCmd(hostname, api_key, cmd)


# Test this
def deactivateLicense(hostname, api_key):
    '''Function to Deactivate / remove license associated with a PA node
    This function is used during decommision of a server and requires internet connectivity
    '''
    cmd = "<request><license><deactivate><VM-Capacity><mode>auto</mode></VM-Capacity></deactivate></license></request>"
    return panOpCmd(hostname, api_key, cmd)


def panSetConfig(hostname, api_key, xpath, element):
    '''Function to make API call to "set" a specific configuration
    '''
    data = {
        'type': 'config',
        'action': 'set',
        'key': api_key,
        'xpath': xpath,
        'element': element
    }
    response = makeApiCall(hostname, data)
    # process response and return success or failure?
    # Debug should print output as well?
    return response


def panGetConfig(hostname, api_key, xpath):
    '''Function to make API call to "get" (or read or list) a specific configuration
    '''
    data = {
        'type': 'config',
        'action': 'get',
        'key': api_key,
        'xpath': xpath
    }
    response = makeApiCall(hostname, data)
    # process response and return success or failure?
    # Debug should print output as well?
    return response


def panEditConfig(hostname, api_key, xpath, element):
    '''Function to make API call to "edit" (or modify) a specific configuration
    Note: Some properties need "set" method instead of "edit" to work
    '''
    data = {
        'type': 'config',
        'action': 'edit',
        'key': api_key,
        'xpath': xpath,
        'element': element
    }
    response = makeApiCall(hostname, data)
    # process response and return success or failure?
    # Debug should print output as well?
    return response


def panRollback(hostname, api_key, username="admin"):
    '''Function to rollback uncommited changes
    '''
    # https://firewall/api/?key=apikey&type=op&cmd=<revert><config><partial><admin><member>admin-name</member></admin></partial></config></revert>
    # panOpCmd(hostname, api_key, cmd)
    cmd = "<revert><config><partial><admin><member>" + username + "</member></admin></partial></config></revert>"
    panOpCmd(hostname, api_key, cmd)


def getTunnelUnits(hostname, api_key):
    '''Function to fet all tunnel interfaces and return it as a list. This is used to find unused tunnel interface id while creating a new one.
    '''
    # Get all tunnel interface ids
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/interface/tunnel/units"
    response = panGetConfig(hostname, api_key, xpath)
    data = XmlDictConfig(xml.etree.ElementTree.XML(response)[0])
    tunnelNames = []
    loop = True
    while loop:
        try:
            tunnelNames.append(data['units']['entry'].pop()['name'])
        except:
            # nothing to left to pop
            loop = False
    return tunnelNames


def getFreeTunnelInfIds(tunnelNames, no_of_ids=2):
    '''Function to return two unused tunnel ids within range 1-9999 and not already used by names in the list 'tunnelNames'
    '''
    # Function to return valid tunnel ids that can be used to create new tunnel interfaces
    range_start = 1
    range_end = 9999
    if len(tunnelNames) == 0:
        return [x for x in range(1, no_of_ids + 1)]
    else:
        currentTunnelIds = [int(name.split('.')[1]) for name in tunnelNames]
        newIds = []
        while len(newIds) < no_of_ids:
            for id in range(range_start, range_end + 1):
                if id not in currentTunnelIds:
                    currentTunnelIds.append(id)
                    newIds.append(id)
                    break
        return newIds


def createIkeGateway(hostname, api_key, name, psk, ikeProfile, pa_dmz_inf, peerIp):
    '''Function to create IKE Gateway
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/ike/gateway/entry[@name='{0}']".format(name)
    element = "<authentication><pre-shared-key><key>{0}</key></pre-shared-key></authentication>\
              <protocol><ikev1><dpd><enable>yes</enable><interval>10</interval><retry>3</retry></dpd>\
              <ike-crypto-profile>{1}</ike-crypto-profile><exchange-mode>main</exchange-mode></ikev1>\
              <ikev2><dpd><enable>yes</enable></dpd></ikev2></protocol><protocol-common><nat-traversal>\
              <enable>no</enable></nat-traversal><fragmentation><enable>no</enable></fragmentation>\
              </protocol-common><local-address><interface>{2}</interface></local-address><peer-address>\
              <ip>{3}</ip></peer-address>".format(psk, ikeProfile, pa_dmz_inf, peerIp)
    # response from SecConfig is return so that incase needed, it can be used to do some processesing
    # In case of failure, Exception should be thrown by makeApiCall itself
    return panSetConfig(hostname, api_key, xpath, element)


def createIpecTunnelInf(hostname, api_key, tunnelInfId, tunnelInfIp="ip/30", mtu=1427):
    '''Function to create tunnel interface to use with IPsec
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/interface/tunnel/units/entry[@name='tunnel.{0}']".format(
        tunnelInfId)
    element = "<ip><entry name='{0}/30'/></ip><mtu>{1}</mtu>".format(tunnelInfIp, mtu)
    # print("Add: IpsecTunnelInf")
    # print(xpath)
    # print(element)
    return panSetConfig(hostname, api_key, xpath, element)


def createIpsecTunnel(hostname, api_key, tunnelName, ikeName, ipsecProfile, tunnelInfId):
    '''Function to create IPSec tunnel
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/tunnel/ipsec/entry[@name='{0}']".format(
        tunnelName)
    element = "<auto-key><ike-gateway><entry name='{0}'/></ike-gateway><ipsec-crypto-profile>{1}</ipsec-crypto-profile></auto-key><tunnel-monitor><enable>no</enable>\
              </tunnel-monitor><tunnel-interface>tunnel.{2}</tunnel-interface>".format(ikeName, ipsecProfile,
                                                                                       tunnelInfId)
    print("Add: Ipsec Tunnel")
    print(xpath)
    print(element)
    return panSetConfig(hostname, api_key, xpath, element)


def addInfToRouter(hostname, api_key, tunnelInfId, virtualRouter="default"):
    '''Function to add an interface to a Virtual-Router
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/interface".format(
        virtualRouter)
    element = "<member>tunnel.{0}</member>".format(tunnelInfId)
    return panSetConfig(hostname, api_key, xpath, element)


def addInfToZone(hostname, api_key, zone, tunnelInfId):
    '''Function to add an interface to a Zone
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/vsys/entry[@name='vsys1']/zone/entry[@name='{0}']/network/layer3".format(
        zone)
    element = "<member>tunnel.{0}</member>".format(tunnelInfId)
    # return panSetConfig(hostname, api_key, xpath, element)
    x = panSetConfig(hostname, api_key, xpath, element)
    print("Adding interface to Zone")
    print(x)


def addToPeerGroup(hostname, api_key, virtualRouter, peerGroup, peerName, tunnel_int_ip, tunnelInfId,
                   tunnel_int_peer_ip, peerAsn):
    '''Add IPSec tunnel interface to a BGP Peer group
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/protocol/bgp/peer-group/entry[@name='{1}']/peer/entry[@name='{2}']".format(
        virtualRouter, peerGroup, peerName)
    element = "<connection-options><incoming-bgp-connection><remote-port>0</remote-port><allow>yes</allow></incoming-bgp-connection><outgoing-bgp-connection><local-port>0</local-port><allow>yes</allow></outgoing-bgp-connection><multihop>0</multihop><keep-alive-interval>10</keep-alive-interval><open-delay-time>0</open-delay-time><hold-time>30</hold-time><idle-hold-time>15</idle-hold-time></connection-options><local-address><ip>{0}</ip><interface>tunnel.{1}</interface></local-address><peer-address><ip>{2}</ip></peer-address><bfd><profile>Inherit-vr-global-setting</profile></bfd><max-prefixes>5000</max-prefixes><peer-as>{3}</peer-as><enable>yes</enable><reflector-client>non-client</reflector-client><peering-type>unspecified</peering-type>".format(
        tunnel_int_ip, tunnelInfId, tunnel_int_peer_ip, peerAsn)
    return panSetConfig(hostname, api_key, xpath, element)


def isLicenseApplied():
    '''Function to check whether license is applied
    '''
    # Todo
    # return true if license is applied
    # return false if no license found
    pass


def isLicenseApiConfigured():
    '''Function to check whether deregister license api key is configured
    '''
    # Todo
    # Check whether license renewal mechanism is configured
    pass


def loadVpnConfigFromS3(bucketName, vpnId):
    '''Function to read AWS-IPSec configuration (xml format) from an S3 bucket, parse it return important data as a dictionary
    '''
    filename = ".".join([vpnId, "xml"])
    s3 = boto3.resource('s3')
    try:
        vpnConf = s3.Object(bucketName, filename).get()['Body'].read().decode('utf-8')
    except:
        print("Error While downloading vpn config xml from s3")
        return False
    ConfigTree = xml.etree.ElementTree.XML(vpnConf)
    Tun1Dict = XmlDictConfig(ConfigTree[-2])
    Tun2Dict = XmlDictConfig(ConfigTree[-1])
    vpnConfDict = {}
    vpnConfDict['id'] = vpnId
    vpnConfDict['pa_dmz_ip'] = Tun1Dict['customer_gateway']['tunnel_outside_address']['ip_address']
    vpnConfDict['pa_asn'] = Tun1Dict['customer_gateway']['bgp']['asn']
    vpnConfDict['vgw_asn'] = Tun1Dict['vpn_gateway']['bgp']['asn']
    vpnConfDict['t1_ike_peer'] = Tun1Dict['vpn_gateway']['tunnel_outside_address']['ip_address']
    vpnConfDict['t1_int_ip'] = Tun1Dict['customer_gateway']['tunnel_inside_address']['ip_address']
    vpnConfDict['t1_int_peer_ip'] = Tun1Dict['vpn_gateway']['tunnel_inside_address']['ip_address']
    vpnConfDict['t1_ike_psk'] = Tun1Dict['ike']['pre_shared_key']
    vpnConfDict['t2_ike_peer'] = Tun2Dict['vpn_gateway']['tunnel_outside_address']['ip_address']
    vpnConfDict['t2_int_ip'] = Tun2Dict['customer_gateway']['tunnel_inside_address']['ip_address']
    vpnConfDict['t2_int_peer_ip'] = Tun2Dict['vpn_gateway']['tunnel_inside_address']['ip_address']
    vpnConfDict['t2_ike_psk'] = Tun2Dict['ike']['pre_shared_key']
    return vpnConfDict


def getVpnConfigurationAndUploadToS3(vpnId, region, bucketName):
    '''Function to download AWS VPN configuration in xml format and upload to S3
    '''
    # IAM Permissions
    # s3:PutObject
    # ec2:DescribeVpnConnections
    client = boto3.client('ec2', region_name=region)
    s3 = boto3.resource('s3')
    try:
        vpnConfig = client.describe_vpn_connections(VpnConnectionIds=[vpnId])['VpnConnections'][0][
            'CustomerGatewayConfiguration']
    except:
        print("Unable to download VPN Configuration")
        return False
    try:
        s3.Object(bucketName, ".".join([vpnId, "xml"])).put(Body=vpnConfig)
    except:
        print("Unable to upload VPN configuration to S3 bucket")
        return False
    return True


def paConfigureVpn(hostname, api_key, vpnConfDict, peerGroup, ikeProfile="default", ipsecProfile="default",
                   pa_dmz_inf="ethernet1/1", virtualRouter="default", zone="UNTRUST"):
    '''Function to configure IPSec vpn on a PA Node
    '''
    try:
        # Configure T1 IKE
        createIkeGateway(hostname, api_key,
                         "-".join(["ike", vpnConfDict['id'], "0"]),
                         vpnConfDict['t1_ike_psk'], ikeProfile,
                         pa_dmz_inf, vpnConfDict['t1_ike_peer'])
        # Configure T2 IKE
        createIkeGateway(hostname, api_key,
                         "-".join(["ike", vpnConfDict['id'], "1"]),
                         vpnConfDict['t2_ike_psk'], ikeProfile,
                         pa_dmz_inf, vpnConfDict['t2_ike_peer'])
        # Get ids to create tunnel Interface
        tunnelInfIds = getFreeTunnelInfIds(getTunnelUnits(hostname, api_key))
        # Configure T1 tunnelInf
        createIpecTunnelInf(hostname, api_key, tunnelInfIds[0],
                            tunnelInfIp=vpnConfDict['t1_int_ip'],
                            mtu=1427)
        addInfToRouter(hostname, api_key, tunnelInfIds[0], virtualRouter)
        addInfToZone(hostname, api_key, zone, tunnelInfIds[0])
        # Configure T2 tunnelInf
        createIpecTunnelInf(hostname, api_key, tunnelInfIds[1],
                            tunnelInfIp=vpnConfDict['t2_int_ip'],
                            mtu=1427)
        addInfToRouter(hostname, api_key, tunnelInfIds[1], virtualRouter)
        addInfToZone(hostname, api_key, zone, tunnelInfIds[1])
        # Configure T1 tunne1
        response1 = createIpsecTunnel(hostname, api_key,
                                      "-".join(["ipsec", vpnConfDict['id'], "0"]),
                                      "-".join(["ike", vpnConfDict['id'], "0"]),
                                      ipsecProfile, tunnelInfIds[0])
        # Configure T2 tuneel
        response2 = createIpsecTunnel(hostname, api_key,
                                      "-".join(["ipsec", vpnConfDict['id'], "1"]),
                                      "-".join(["ike", vpnConfDict['id'], "1"]),
                                      ipsecProfile, tunnelInfIds[1])
        # Add T1 to peer group
        response3 = addToPeerGroup(hostname, api_key, "default", peerGroup,
                                   "-".join(["peer", vpnConfDict['id'], "0"]),
                                   "".join([vpnConfDict['t1_int_ip'], "/30"]),
                                   tunnelInfIds[0], vpnConfDict['t1_int_peer_ip'],
                                   vpnConfDict['vgw_asn'])
        # Add T2 to peer group
        response4 = addToPeerGroup(hostname, api_key, "default", peerGroup,
                                   "-".join(["peer", vpnConfDict['id'], "1"]),
                                   "".join([vpnConfDict['t2_int_ip'], "/30"]),
                                   tunnelInfIds[1], vpnConfDict['t2_int_peer_ip'],
                                   vpnConfDict['vgw_asn'])
        # return response
    except:
        print("PA VPN configuration failed", sys.exc_info()[0])
        return False

    return [response1, response2, response3, response4]
    # return True


def editIpObject(hostname, api_key, name, value):
    '''Function to edit/update an existing IP Address object on a PA Node
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/vsys/entry[@name='vsys1']/address/entry[@name='{0}']/ip-netmask".format(
        name)
    element = "<ip-netmask>{0}</ip-netmask>".format(value)
    return panEditConfig(hostname, api_key, xpath, element)


def updateRouterIdAndAsn(hostname, api_key, routerId, routerAsn, virtualRouter="default"):
    '''Function to edit/update BGP RourterID(Public IP) and ASN on a PA Node
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/protocol/bgp".format(
        virtualRouter)
    element = "<router-id>{0}</router-id><local-as>{1}</local-as>".format(routerId, routerAsn)
    return panSetConfig(hostname, api_key, xpath, element)


def updateDefaultRouteNextHope(hostname, api_key, subnetGateway, virtualRouter="default"):
    '''Function to update default route virtual router
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/routing-table/ip/static-route/entry[@name='default']/nexthop".format(
        virtualRouter)
    element = "<ip-address>{0}</ip-address>".format(subnetGateway)
    return panSetConfig(hostname, api_key, xpath, element)


def pa_initialize(hostname, api_key, pa_dmz_priv_ip, pa_dmz_pub_ip, pa_asn, pa_dmz_subnet_gw, SubnetCidr,
                  license_api_key=""):
    '''Function to initialize PA node
    '''
    # Update 'eth1' object with private IP of eth1 interface
    mask = SubnetCidr.split("/")[1]
    response1 = editIpObject(hostname, api_key, "eth1", "/".join([pa_dmz_priv_ip, mask]))
    # Update BGP router ID with public IP of eth1 and BGP ASN
    response2 = updateRouterIdAndAsn(hostname, api_key, pa_dmz_pub_ip, pa_asn)
    # Update next hop of static route to match subnet gw
    response3 = updateDefaultRouteNextHope(hostname, api_key, pa_dmz_subnet_gw)
    # Add ApiKey to deactivate License
    response4 = configDeactivateLicenseApiKey(hostname, api_key, license_api_key)
    return [response1, response2, response3, response4]


def paGroupSetupPaPeers(api_key, newPaGroup, paGroupList):
    """
    Function to configure BGP peering between a new PAGroup and existing PAGroups. ActiveNode/PassiveNode of new PA
    group will be peered with corresponding node in exising PA groups.
    :param api_key: api_key to auth with
    :param newPaGroup: newPaGroup info
    :param paGroupList: All of the entries of pa group info in DynamoDB table
    :return: True or False
    """
    failed = False
    for paGroup in paGroupList:
        if paGroup['PaGroupName'] != newPaGroup['PaGroupName'] and 'N1Pip' in paGroup.keys():
            # Configure newPaGroup.N1 <--> paGroup.N1
            peerGroup = "Active"
            pa_add_paPeer(newPaGroup['N1Mgmt'], api_key, peerGroup,
                          "-".join([newPaGroup['PaGroupName'], "N1", paGroup['PaGroupName'], "N1"]),
                          paGroup['N1Pip'], paGroup['N1Asn'])

            # Configure paGroup.N1 <--> newPaGroup.N1
            pa_add_paPeer(paGroup['N1Mgmt'], api_key, peerGroup,
                          "-".join([paGroup['PaGroupName'], "N1", newPaGroup['PaGroupName'], "N1"]),
                          newPaGroup['N1Pip'], newPaGroup['N1Asn'])

            # Configure newPaGroup.N2 <--> paGroup.N2
            peerGroup = "Passive"
            pa_add_paPeer(newPaGroup['N2Mgmt'], api_key, peerGroup,
                          "-".join([newPaGroup['PaGroupName'], "N2", paGroup['PaGroupName'], "N2"]),
                          paGroup['N2Pip'], paGroup['N2Asn'])
            # Configure paGroup.N2 <--> newPaGroup.N2
            pa_add_paPeer(paGroup['N2Mgmt'], api_key, peerGroup,
                          "-".join([paGroup['PaGroupName'], "N2", newPaGroup['PaGroupName'], "N2"]),
                          newPaGroup['N2Pip'], newPaGroup['N2Asn'])
            # TODO:
            # if above function fails:
            # failed = True
            # report error
            # break this look to roll back changes on all nodes
    if not failed:
        # call commit on all nodes
        for paGroup in paGroupList:
            if 'N1Mgmt' in paGroup.keys():
                panCommit(paGroup['N1Mgmt'], api_key,
                          message="Create bgp peer from Active node of PaGroup {0} to active nodes of other PA groups".format(
                              newPaGroup['PaGroupName']))
                panCommit(paGroup['N2Mgmt'], api_key,
                          message="Create bgp peer from Passive node of PaGroup {0} to active nodes of other PA groups".format(
                              newPaGroup['PaGroupName']))
        return True
    else:
        # call rollback on all nodes
        return False


def pa_add_paPeer(hostname, api_key, peerGroup, peerName, pa_peer_ip, peerAsn, virtualRouter="default",
                  tunnelInf="ethernet1/1"):
    '''Function to add PA node to a BGP peer group
    NOTE: This is slightly different from adding tunnel interface to BGP Peer group, thus a separate function
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/protocol/bgp/peer-group/entry[@name='{1}']/peer/entry[@name='{2}']".format(
        virtualRouter, peerGroup, peerName)
    element = "<connection-options><incoming-bgp-connection><remote-port>0</remote-port><allow>yes</allow></incoming-bgp-connection><outgoing-bgp-connection><local-port>0</local-port><allow>yes</allow></outgoing-bgp-connection><multihop>0</multihop><keep-alive-interval>10</keep-alive-interval><open-delay-time>0</open-delay-time><hold-time>30</hold-time><idle-hold-time>15</idle-hold-time></connection-options><local-address><interface>{0}</interface></local-address><peer-address><ip>{1}</ip></peer-address><bfd><profile>Inherit-vr-global-setting</profile></bfd><max-prefixes>5000</max-prefixes><peer-as>{2}</peer-as><enable>yes</enable><reflector-client>non-client</reflector-client><peering-type>unspecified</peering-type>".format(
        tunnelInf, pa_peer_ip, peerAsn)
    return panSetConfig(hostname, api_key, xpath, element)


def pa_create_named_configuration_backup():
    '''Function to create a named configuration backup.
    This may be useful incase of restoring PA Node to a specific point
    '''
    pass


def createNewPaGroup(region, stackName, templateUrl, paGroupName, sshKey, transitVpcMgmtAz1, transitVpcMgmtAz2,
                     transitVpcDmzAz1, transitVpcDmzAz2, transitVpcTrustedSecurityGroup,
                     transitVpcUntrustedSecurityGroup,
                     paGroupInstanceProfile, paBootstrapBucketName, Node1Asn, Node2Asn, transitVpcDmzAz1SubnetGateway,
                     transitVpcDmzAz2SubnetGateway):
    '''Create new PA group by running a Cloudformation template
    '''
    parameters = [
        {'ParameterKey': 'paGroupName', 'ParameterValue': paGroupName},
        {'ParameterKey': 'sshKey', 'ParameterValue': sshKey},
        {'ParameterKey': 'transitVpcMgmtAz1', 'ParameterValue': transitVpcMgmtAz1},
        {'ParameterKey': 'transitVpcMgmtAz2', 'ParameterValue': transitVpcMgmtAz2},
        {'ParameterKey': 'transitVpcDmzAz1', 'ParameterValue': transitVpcDmzAz1},
        {'ParameterKey': 'transitVpcDmzAz2', 'ParameterValue': transitVpcDmzAz2},
        {'ParameterKey': 'transitVpcTrustedSecurityGroup', 'ParameterValue': transitVpcTrustedSecurityGroup},
        {'ParameterKey': 'transitVpcUntrustedSecurityGroup', 'ParameterValue': transitVpcUntrustedSecurityGroup},
        {'ParameterKey': 'paGroupInstanceProfile', 'ParameterValue': paGroupInstanceProfile},
        {'ParameterKey': 'paBootstrapBucketName', 'ParameterValue': paBootstrapBucketName},
        {'ParameterKey': 'Node1Asn', 'ParameterValue': Node1Asn},
        {'ParameterKey': 'Node2Asn', 'ParameterValue': Node2Asn},
        {'ParameterKey': 'transitVpcDmzAz1SubnetGateway', 'ParameterValue': transitVpcDmzAz1SubnetGateway},
        {'ParameterKey': 'transitVpcDmzAz2SubnetGateway', 'ParameterValue': transitVpcDmzAz2SubnetGateway}
    ]
    client = boto3.client('cloudformation', region_name=region)
    response = client.create_stack(
        StackName=stackName,
        TemplateURL=templateUrl,
        # TemplateBody='string',
        Parameters=parameters,
        TimeoutInMinutes=15,
        OnFailure='ROLLBACK'
    )
    return response


def parseStackOutput(stackName, region):
    '''
    Function to parse stack output (PAGroup), convert it into a Dictionary and return it
    '''
    client = boto3.client('cloudformation', region_name=region)
    status = client.describe_stacks(StackName=stackName)
    if status['Stacks'][0]['StackStatus'] == "CREATE_IN_PROGRESS":
        return "Wait"
    elif status['Stacks'][0]['StackStatus'] == "CREATE_COMPLETE" or status['Stacks'][0][
        'StackStatus'] == "UPDATE_COMPLETE":
        outputs = {}
        for entry in status['Stacks'][0]['Outputs']:
            outputs[entry['OutputKey']] = entry['OutputValue']
        return outputs
    else:
        print("Error while creating stack:{0} with status {1}".format(stackName, status['Stacks'][0]['StackStatus']))
        return None


def paGroupInitialize(api_key, paGroup, DeLicenseApiKey=""):
    '''
    Function to initialize a PA Group (Both nodes)
    '''
    # Initialize NODE1
    result1 = pa_initialize(paGroup['N1Mgmt'], api_key, paGroup['N1Pip'], paGroup['N1Eip'], paGroup['N1Asn'],
                            paGroup['Az1SubnetGw'], paGroup['Az1SubnetCidr'], DeLicenseApiKey)
    # Initialize NODE2
    result2 = pa_initialize(paGroup['N2Mgmt'], api_key, paGroup['N2Pip'], paGroup['N2Eip'], paGroup['N2Asn'],
                            paGroup['Az2SubnetGw'], paGroup['Az2SubnetCidr'], DeLicenseApiKey)
    # TODO: 
    # commit if both results are success and return success
    # else return False
    panCommit(paGroup['N1Mgmt'], api_key, message="Initialization completed")
    panCommit(paGroup['N2Mgmt'], api_key, message="Initialization completed")
    # Return False  if something fails 
    return [result1, result2]


def paGroupConfigureVpn(api_key, paGroup, vpnConfigBucket, N1VpnId, N2VpnId, ikeProfile="default",
                        ipsecProfile="default", pa_dmz_inf="ethernet1/1", virtualRouter="default",
                        zone="UNTRUST"):
    '''Function to configure VPN with a PAGroup and a VPC. Each node in the PAGroup will establish a VPN with the VPC.
    '''
    # Configure VPN on Node1
    vpnN1Conf = loadVpnConfigFromS3(vpnConfigBucket, N1VpnId)
    peerGroup = "Active"  # Incase needed, this can come from PaGroupInfo eg: paGroup['PaN1Type'] = "Active"
    N1VpnStatus = paConfigureVpn(paGroup['N1Mgmt'], api_key, vpnN1Conf, peerGroup, ikeProfile, ipsecProfile, pa_dmz_inf,
                                 virtualRouter, zone)

    # Configure VPN on Node2
    vpnN2Conf = loadVpnConfigFromS3(vpnConfigBucket, N2VpnId)
    peerGroup = "Passive"  # Incase needed, this can come from PaGroupInfo eg: paGroup['PaN1Type'] = "Active"
    N2VpnStatus = paConfigureVpn(paGroup['N2Mgmt'], api_key, vpnN2Conf, peerGroup, ikeProfile, ipsecProfile, pa_dmz_inf,
                                 virtualRouter, zone)

    # Return False if something fails
    if not N1VpnStatus or not N2VpnStatus:
        panRollback(paGroup['N1Mgmt'], api_key)
        panRollback(paGroup['N2Mgmt'], api_key)
        return False
    else:
        panCommit(paGroup['N1Mgmt'], api_key, message="VpnConfigured N1VpnId: {}".format(N1VpnId))
        panCommit(paGroup['N2Mgmt'], api_key, message="VpnConfigured N2VpnId: {}".format(N2VpnId))
        return True


def panDelConfig(hostname, api_key, xpath):
    '''Function to delete delete a configuration
    '''
    data = {
        'type': 'config',
        'action': 'delete',
        'key': api_key,
        'xpath': xpath
    }
    response = makeApiCall(hostname, data)
    return response


def paGroupDelPaPeers(api_key, newPaGroup, paGroupList):
    '''Function to remove a PAGroup from existing BGP peer network. This is done by deleting entries related to N1/N2 of the PAGroup from other active PAGroups.
    This need to be done before decommisioning a PAGroup
    '''
    failed = False
    for paGroup in paGroupList:
        if paGroup['PaGroupName'] == newPaGroup['PaGroupName']:
            continue

        # Remove newPaGroup.N1 <--> paGroup.N1
        peerGroup = "Active"
        deleteFromPeerGroup(newPaGroup['N1Mgmt'], api_key, peerGroup,
                            "-".join([newPaGroup['PaGroupName'], "N1", paGroup['PaGroupName'], "N1"]),
                            virtualRouter="default")

        # Remove paGroup.N1 <--> newPaGroup.N1
        deleteFromPeerGroup(paGroup['N1Mgmt'], api_key, peerGroup,
                            "-".join([paGroup['PaGroupName'], "N1", newPaGroup['PaGroupName'], "N1"]),
                            virtualRouter="default")

        # Remove newPaGroup.N2 <--> paGroup.N2
        peerGroup = "Passive"
        deleteFromPeerGroup(newPaGroup['N2Mgmt'], api_key, peerGroup,
                            "-".join([newPaGroup['PaGroupName'], "N2", paGroup['PaGroupName'], "N2"]),
                            virtualRouter="default")

        ## Remove paGroup.N2 <--> newPaGroup.N2
        deleteFromPeerGroup(paGroup['N2Mgmt'], api_key, peerGroup,
                            "-".join([paGroup['PaGroupName'], "N2", newPaGroup['PaGroupName'], "N2"]),
                            virtualRouter="default")

    if not failed:
        # call commit on all nodes
        for paGroup in paGroupList:
            panCommit(paGroup['N1Mgmt'], api_key,
                      message="Remove bgp peer entries related to paGroup {0}".format(newPaGroup['PaGroupName']))
            panCommit(paGroup['N2Mgmt'], api_key,
                      message="Remove bgp peer entries related to paGroup {0}".format(newPaGroup['PaGroupName']))
        return True
    else:
        return False


def paGroupDeleteVpn(api_key, paGroup, N1VpnId, N2VpnId):
    '''Function to delete IPSec VPN configuration between a PAGroup (both nodes) and a VPC
    '''
    # node1
    pa_delete_ipsec_vpn(paGroup['N1Mgmt'], api_key, N1VpnId, "Active")
    # Commit
    print("commit: ")
    panCommit(paGroup['N1Mgmt'], api_key, "Delete vpn configuration")

    # node2
    pa_delete_ipsec_vpn(paGroup['N2Mgmt'], api_key, N2VpnId, "Passive")
    # Commit
    print("commit: ")
    panCommit(paGroup['N2Mgmt'], api_key, "Delete vpn configuration")


def pa_delete_ipsec_vpn(hostname, api_key, vpnId, peerGroup):
    '''Function to delete IPSec vpn on a PA Node
    '''
    ipsec_1_name = "-".join(["ipsec", vpnId, "0"])
    ipsec_2_name = "-".join(["ipsec", vpnId, "1"])
    ike_gw_1 = "-".join(["ike", vpnId, '0'])
    ike_gw_2 = "-".join(["ike", vpnId, '1'])
    print("getting the tunnel interfaced from ipsec")
    tun1 = get_tun_inf_from_ipsec(hostname, api_key, ipsec_1_name)
    tun2 = get_tun_inf_from_ipsec(hostname, api_key, ipsec_2_name)
    peer_1_Name = "-".join(["peer", vpnId, '0'])
    peer_2_Name = "-".join(["peer", vpnId, '1'])

    # Deleting ipsec tunnel
    deleteIpsecTunnel(hostname, api_key, ipsec_1_name)
    deleteIpsecTunnel(hostname, api_key, ipsec_2_name)

    # Deleting entry from peer group before deleting tun inf
    deleteFromPeerGroup(hostname, api_key, peerGroup, peer_1_Name, virtualRouter="default")
    deleteFromPeerGroup(hostname, api_key, peerGroup, peer_2_Name, virtualRouter="default")

    # Deleting IKEs
    deleteIkeGateway(hostname, api_key, ike_gw_1)
    deleteIkeGateway(hostname, api_key, ike_gw_2)

    # Disassociate the tunnel interfaces with the Virtual Router
    removeInfFromRouter(hostname, api_key, tun1, virtualRouter="default")
    removeInfFromRouter(hostname, api_key, tun2, virtualRouter="default")

    # Disassociate the tunnel interfaces with the Virtual Zone
    removeInfFromZone(hostname, api_key, tun1, zone="UNTRUST")
    removeInfFromZone(hostname, api_key, tun2, zone="UNTRUST")

    # Deleting Ipsec tunnel interfaces
    deleteIpecTunnelInf(hostname, api_key, tun1)
    deleteIpecTunnelInf(hostname, api_key, tun2)


def get_tun_inf_from_ipsec(hostname, api_key, tunnelName):
    '''Function to fetch tunnel interface associated with an IPSec configuration
    '''
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/tunnel/ipsec/entry[@name='{0}']".format(
        tunnelName)
    result = panGetConfig(hostname, api_key, xpath)
    exp = re.compile('>(tunnel\.[0-9]+)<')
    return exp.findall(str(result))[0]


def deleteIpsecTunnel(hostname, api_key, tunnelName):
    '''Function to delete IPSec tunnel
    '''
    print("Deleting ipsec tunnel: ", tunnelName)
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/tunnel/ipsec/entry[@name='{0}']".format(
        tunnelName)
    result = panDelConfig(hostname, api_key, xpath)
    return result


def deleteFromPeerGroup(hostname, api_key, peerGroup, peerName, virtualRouter):
    '''Function to remove tun interface from peerGroup
    '''
    print("Remove tunnel interface from peer group: ", peerGroup)
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/protocol/bgp/peer-group/entry[@name='{1}']/peer/entry[@name='{2}']".format(
        virtualRouter, peerGroup, peerName)
    result = panDelConfig(hostname, api_key, xpath)
    return result


def removeInfFromRouter(hostname, api_key, tunnelInfId, virtualRouter):
    '''Function to disassociate the tunnel interfaces from Virtual Router
    '''
    print("Disassociating the tunnel inf from virtual router")
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/virtual-router/entry[@name='{0}']/interface/member[text()='{1}']".format(
        virtualRouter, tunnelInfId)
    result = panDelConfig(hostname, api_key, xpath)
    return result


def removeInfFromZone(hostname, api_key, tunnelInfId, zone):
    '''Function to disassociate the tunnel interfaces from Zone
    '''
    print("Disassociate the tunnel interfaces with the Zone")
    xpath = "/config/devices/entry[@name='localhost.localdomain']/vsys/entry[@name='vsys1']/zone/entry[@name='{0}']/network/layer3/member[text()='{1}']".format(
        zone, tunnelInfId)
    result = panDelConfig(hostname, api_key, xpath)
    return result


def deleteIpecTunnelInf(hostname, api_key, tunnelInfId):
    '''Function to delete Ipsec tunnel interface
    '''
    print("Delete Ipsec tunnel interface: ", tunnelInfId)
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/interface/tunnel/units/entry[@name='{0}']".format(
        tunnelInfId)
    result = panDelConfig(hostname, api_key, xpath)
    return result


def deleteIkeGateway(hostname, api_key, ikeName):
    '''Function to delete IKE Gateway
    '''
    print("Delete Ike gateway: ", ikeName)
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/ike/gateway/entry[@name='{0}']".format(
        ikeName)
    result = panDelConfig(hostname, api_key, xpath)
    return result
