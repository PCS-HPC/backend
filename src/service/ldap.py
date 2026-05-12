from passlib.hash import ldap_salted_sha1
from fastapi import HTTPException
from ldap3 import Server, Connection, ALL, MODIFY_REPLACE, MODIFY_ADD, SUBTREE
from pydantic import BaseModel
from typing import Literal
from pathlib import Path
import os

raw_storage_root = os.getenv("LOCAL_STORAGE_DIR", "storage")
STORAGE_ROOT = Path(os.path.expandvars(os.path.expanduser(raw_storage_root))).resolve()
LDAP_DOMAIN = os.getenv("LDAP_DOMAIN")
LDAP_ADMIN_USER = os.getenv("LDAP_ADMIN_USER")
LDAP_ADMIN_PASSWORD = os.getenv("LDAP_ADMIN_PASSWORD")
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN")
POOL_DN = f'cn=next-free-id,{LDAP_BASE_DN}'

class User(BaseModel):
    username: str
    password: str
    uidNumber: int = 0
    gidNumber: int = 0

class Group(BaseModel):
    name: str
    gidNumber: int

class PasswordChange(BaseModel):
    password: str

def get_ldap_connection() -> Connection:
    server = Server(LDAP_DOMAIN, get_info=ALL)
    conn = Connection(server, LDAP_ADMIN_USER, LDAP_ADMIN_PASSWORD, auto_bind=True)
    print("LDAP Connection Success")
    return conn

# OpenLDAP do not have Distributed Numeric Assignment Plugin (DNA), so we need to figure out the uid and gid by ourselves
# we created a dummy user, and the current uid and gid is saved in that user
# all we need to do is just retrieve the current uid and gid, and thats the new user's uid
# then we increment the id and save it back to the dummy user
def get_next_uid(ldap: Connection, scope: Literal['uidNumber', 'gidNumber'] = 'uidNumber'):
    ldap.search(
        search_base=POOL_DN, 
        search_filter='(cn=next-free-id)', 
        attributes=[scope]
    )

    current_uid = int(ldap.entries[0][scope].value)
    return current_uid

def update_next_uids(ldap: Connection, next_uid, scope: Literal['uidNumber', 'gidNumber'] = 'uidNumber'):
    ldap.modify(POOL_DN, {
        scope: [(MODIFY_REPLACE, [next_uid])],
    })

def create_user_with_group(user: User, ldap: Connection) -> dict:
    uid = get_next_uid(ldap)
    gid = get_next_uid(ldap, 'gidNumber')

    group = Group(
        name=user.username,
        gidNumber=gid
    )

    user.uidNumber = uid
    user.gidNumber = gid

    group_result = create_group(group, ldap)
    update_next_uids(ldap, gid + 1, 'gidNumber')
    if group_result['result']:
        return group_result
    user_result = create_user(user, ldap)
    update_next_uids(ldap, uid + 1, 'uidNumber')

    return user_result

def create_user(user: User, ldap: Connection) -> dict:
    """
    Check return_val['result']
    if == 0, succcess! 
    else, failed, check return_val['description'] for reason

    Can throw exceptions
    LDAPEntryAlreadyExistsResult = user with user.username already exist
    """

    # gng get_user_storage_dir should be in util
    home_dir = (STORAGE_ROOT / user.username).resolve()
    password_hash = ldap_salted_sha1.hash(user.password)
    user_dn = f"uid={user.username},ou=users,{LDAP_BASE_DN}"

    # Add user
    ldap.add(
        user_dn,
        object_class=['top', 'posixAccount', 'inetOrgPerson', 'shadowAccount'],
        attributes={
            'cn': user.username,
            'sn': user.username,
            'uid': user.username,
            'homeDirectory': home_dir,
            'loginShell': '/bin/bash',
            'gidNumber': user.gidNumber,
            'uidNumber': user.uidNumber,
            'userPassword': password_hash
        }
    )
    return ldap.result

def create_group(group: Group, ldap: Connection) -> dict:
    """
    Check return_val['result']
    if == 0, succcess! 
    else, failed, check return_val['description'] for reason

    Can throw exceptions
    LDAPEntryAlreadyExistsResult = group with group.name already exist
    """
    group_dn = f"cn={group.name},ou=groups,{LDAP_BASE_DN}"
        
    ldap.add(
        group_dn,
        object_class=['top', 'posixGroup'],
        attributes= {
            'cn': group.name,
            'gidNumber': group.gidNumber
        }
    )
    return ldap.result

# BELOW FUNCTIONS ARE UTIL FUNCTIONS
# dont think these is used, just includead just in case
def list_users(ldap: Connection) -> dict:
    ldap.search(
        search_base=f"ou=users,{LDAP_BASE_DN}",
        search_filter="(objectClass=posixAccount)",
        attributes=['uid', 'cn', 'uidNumber', 'gidNumber', 'homeDirectory', 'loginShell']
    )
    
    users = []
    for entry in ldap.entries:
        users.append({
            "dn": entry.entry_dn,
            "username": str(entry.uid),
            "uid_number": int(entry.uidNumber),
            "gid_number": int(entry.gidNumber),
            "home_directory": str(entry.homeDirectory),
            "shell": str(entry.loginShell)
        })

    return {"users": users, "count": len(users)}

def list_groups(ldap: Connection) -> dict:    
    ldap.search(
        search_base=f"ou=groups,{LDAP_BASE_DN}",
        search_filter="(objectClass=posixGroup)",
        attributes=['cn', 'gidNumber', 'memberUid']
    )
    
    groups = []
    for entry in ldap.entries:
        groups.append({
            "dn": entry.entry_dn,
            "name": str(entry.cn),
            "gid_number": int(entry.gidNumber),
            "members": [str(m) for m in entry.memberUid] if 'memberUid' in entry else []
        })
    
    return {"groups": groups, "count": len(groups)}

def get_user(username: str, ldap: Connection) -> dict:    
    user_dn = f"uid={username},ou=users,{LDAP_BASE_DN}"
    ldap.search(
        search_base=user_dn,
        search_filter="(objectClass=posixAccount)",
        search_scope='BASE',
        attributes=['uid', 'cn', 'uidNumber', 'gidNumber', 'homeDirectory', 'loginShell']
    )
    
    if not ldap.entries:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    
    entry = ldap.entries[0]
    user = {
        "dn": entry.entry_dn,
        "username": str(entry.uid),
        "uid_number": int(entry.uidNumber),
        "gid_number": int(entry.gidNumber),
        "home_directory": str(entry.homeDirectory),
        "shell": str(entry.loginShell)
    }
    return user

def delete_user(username: str, ldap: Connection) -> dict:
    """
    Check return_val['result']
    if == 0, succcess! 
    else, failed, check return_val['description'] for reason

    Can throw exceptions
    LDAPNoSuchObjectResult = cant find user
    """
    user_dn = f"uid={username},ou=users,{LDAP_BASE_DN}"
    ldap.delete(user_dn)
    return ldap.result

def change_password(username: str, password_change: PasswordChange, ldap: Connection) -> dict:
    """
    Check return_val['result']
    if == 0, succcess! 
    else, failed, check return_val['description'] for reason

    Can throw exceptions
    LDAPNoSuchObjectResult = cant find user
    """
    user_dn = f"uid={username},ou=users,{LDAP_BASE_DN}"
    
    password_hash = ldap_salted_sha1.hash(password_change.password)
    
    ldap.modify(
        user_dn,
        {'userPassword': [(MODIFY_REPLACE, [password_hash])]}
    )
    return ldap.result

def add_user_to_group(group_name: str, username: str, ldap: Connection) -> dict:
    """
    Check return_val['result']
    if == 0, succcess! 
    else, failed, check return_val['description'] for reason

    Can throw exceptions
    LDAPNoSuchObjectResult = cant find group
    """
    group_dn = f"cn={group_name},ou=groups,{LDAP_BASE_DN}"
    
    ldap.modify(
        group_dn,
        {'memberUid': [(MODIFY_ADD, [username])]}
    )
    return ldap.result
