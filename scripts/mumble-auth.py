﻿#!/usr/bin/env python
# -*- coding: utf-8
#
#    mumble-auth.py - Sample script to show the basics of using server controlled
#                     context menu entries for in-client registration tickets.
#
#    Requirements:
#        * python 2.5 or higher
#        * cherrypy 3 or higher
#        * python ice bindings
#        * murmur + mumble rev 1530 or higher 

import cherrypy
import Ice
from threading import Semaphore
import random, time

#
#--- Config stuff
#
baseurl = "http://localhost:8080/register?id=" # Baseurl for registrations
storage_time = 10*24*60*60 # Time in seconds a reg entry is guaranteed to be valid
proxy = "Meta:tcp -h 127.0.0.1 -p 6502"
group = "admin" # ACL group which has the right to send regurls
port = 8080 # Cherrypy port
slice = "Murmur.ice"
production = False # Set this to true to surpress tracebacks

# Runtime generate bindings
Ice.loadSlice(slice)
import Murmur

# Global vars
sema_ids = Semaphore()
ids = {}  #Contains list(sid, user, time)


class MetaCallbackI(Murmur.MetaCallback):
    def started(self, s, current=None):
        serverR = Murmur.ServerCallbackPrx.uncheckedCast(adapter.addWithUUID(ServerCallbackI(server, current.adapter)))
        s.addCallback(serverR)
    def stopped(self, s, current=None): pass # Unused callback

class ServerCallbackI(Murmur.ServerCallback):
    def __init__(self, server, adapter):
        self.server = server
        self.contextR=Murmur.ServerContextCallbackPrx.uncheckedCast(adapter.addWithUUID(ServerContextCallbackI(server)))

    def playerConnected(self, p, current=None):
        # Check if the user is in the right acl class and add the context menu
        allowed = False
        for acl in self.server.getACL(0)[1]:
            if acl.name == group and p.playerid in acl.members:
                allowed = True
                break
        if allowed:
            self.server.addContextCallback(p.session,
                                           "sendregurl",
                                           "Send registration URL",
                                           self.contextR, Murmur.ContextPlayer)
    def playerDisconnected(self, p, current=None): pass # Unused callbacks
    def playerStateChanged(self, p, current=None): pass
    def channelCreated(self, c, current=None): pass
    def channelRemoved(self, c, current=None): pass
    def channelStateChanged(self, c, current=None): pass

class ServerContextCallbackI(Murmur.ServerContextCallback):
    #--- Server message template strings
    err_notallowed = "You are not allowed to send registration urls"
    msg_regurl = "You've been allowed to register with this mumble server, " \
                 "please <a href='%(url)s'>click here to register</a>."
    
    
    def __init__(self, server):
      self.server = server

    def contextAction(self, action, p, session, chanid, current=None):
        if action == "sendregurl" and chanid == 0:
            # Check if user is in the right acl group
            allowed = False
            for acl in self.server.getACL(0)[1]:
                if acl.name == group and p.playerid in acl.members:
                    allowed = True
                    break
            if not allowed:
                self.server.sendMessage(p, self.err_notallowed)
                return
                    
            sema_ids.acquire()
            try:
                # Take the chance to cleanup old entries
                todel = []
                for key, reg in ids.iteritems():
                    if int(time.time()) - reg[2] > storage_time:
                        todel.append(key)
                for key in todel:
                    del ids[key]
                
                # Ok, now generate his registration id (64bit)
                rid = None
                while not rid or rid in ids:
                    rid = random.randrange(0, pow(2,64))
                sid = self.server.id()
                
                # Remember his username
                try:
                    username = self.server.getState(session).name
                except Murmur.InvalidSessionException:
                    username = ""
                
                # Save everything
                ids[str(rid)] = (sid, username, int(time.time()))
                # Send reg url to the player
                url = baseurl + str(rid)
                self.server.sendMessage(session,
                                        self.msg_regurl % {'url':url})
            finally:
                sema_ids.release()


    
class mumble_auth(object):
    #--- Web template strings
    template = """<?xml version="1.0" encoding="utf-8" ?>
    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
        <head>
            <title>%(title)s</title>
        </head>
        <body>
        <h1>%(title)s</h1>
        %(body)s
        </body>
    </html>"""
    
    err_id = """<h2>Invalid ID</h2>
    The ID for your registration has already been used or is invalid.</br>
    Please request a new registreation link from a Mumble administrator.</br>"""
    
    err_username = """<h2>Invalid username</h2>
    The username you chose contains characters which are not allowed.<br/>
    Please only use normal characters without whitespaces.</br>"""
    
    err_username_existing = """<h2>Username already registered</h2>
    The username you chose is already registered on this server.</br>
    Please choose another one.</br>"""
    
    err_password = """<h2>Invalid password</h2>
    The password you chose didn't match the criterias enforced by this server.<br/>
    Your password should be at least 6 characters long.</br>"""
    
    err_password_mismatch = """<h2>Passwords do not match</h2>
    The password you entered did not match the one in the confirmation box.<br/>
    Make sure both boxes contain the same password.</br>"""
    
    snippet_retry = '<br/><a href="%(url)s">Click here to try again</a>'
    
    body_index = """This is the mumble-auth script, to be able to register yourself
    an account please ask a admin on the mumble server."""
    
    body_complete = """<h2>Success</h2>
    You have been registered with the server successfully,</br>
    please try to login to the server with your new login credentials!"""
    
    body_regform = """<h2>Enter user information</h2>
    <form action="doregister" method="post">
        <p>Username</p>
        <input type="text" name="username" value="%(username)s" 
            size="15" maxlength="40"/>
        <p>Password</p>
        <input type="password" name="password" value="" 
            size="10" maxlength="40"/>
        <p>Confirm password</p>
        <input type="password" name="cpassword" value="" 
            size="10" maxlength="40"/>
        <input type="hidden" name="id" value="%(id)s"
        <p><input type="submit" value="Register"/></p>
        <p><input type="reset" value="Clear"/></p>
    </form>"""
                
    def __init__(self, murmur):
        self.murmur = murmur
        
    def index(self):
        title = "Mumble Auth - Index"
        return self.template % {'title':title,
                                'body':self.body_index}
    index.exposed = True
    
    def register(self, id = None):
        title = "Mumble Auth - Register";
        if not id in ids:
            body = self.err_id # Invalid ID
        else:
            # In case of a valid ID
            body = self.body_regform % {'username':ids[id][1],
                                        'id':id}
            
        return self.template % {'title':title,
                                'body':body}
    register.exposed = True

    def doregister(self, id = None, username = None, password = None, cpassword = None):
        title = "Mumble Auth - Register";
        sema_ids.acquire()
        try:
            # Check if all parameters are ok
            if not id in ids:
                body = self.err_id # Invalid id
            elif not username or " " in username: # Invalid username
                body = self.err_username + \
                        self.snippet_retry % {'url':baseurl+id}
            elif len(password) < 6:  # Password criteria didn't match
                body = self.err_password + \
                        self.snippet_retry % {'url':baseurl+id}
            elif password != cpassword: # Password mismatch
                body = self.err_password_mismatch + \
                        self.snippet_retry % {'url':baseurl+id}
            else:
                # Ok, try to register him
                server = self.murmur.getServer(ids[id][0])
                if (len(server.getRegisteredPlayers(username))!=0):
                    body = self.err_username_existing + \
                            self.snippet_retry % {'url':baseurl+id}
                else:
                    # Register player
                    pid = server.registerPlayer(username)
                    reg = server.getRegistration(pid)
                    reg.pw = password
                    server.updateregistration(reg)
                    # Void registration id
                    del ids[id]
                    # Success
                    body = self.body_complete
        finally:
            sema_ids.release()
        return self.template % {'title':title,
                                'body':body}
    doregister.exposed = True
    
if __name__ == "__main__":
    random.seed()
    ice = Ice.initialize()
    try:
        meta = Murmur.MetaPrx.checkedCast(ice.stringToProxy(proxy))
        adapter = ice.createObjectAdapterWithEndpoints("Callback.Client", "tcp -h 127.0.0.1")
        metaR=Murmur.MetaCallbackPrx.uncheckedCast(adapter.addWithUUID(MetaCallbackI()))
        adapter.activate()
        
        meta.addCallback(metaR)
        for server in meta.getBootedServers():
            serverR=Murmur.ServerCallbackPrx.uncheckedCast(adapter.addWithUUID(ServerCallbackI(server, adapter)))
            server.addCallback(serverR)

        if production: cherrypy.config.update({'environment': 'production'})
        cherrypy.server.socket_port = port
        cherrypy.quickstart(mumble_auth(meta))
    finally:
        ice.shutdown()
        ice.waitForShutdown()