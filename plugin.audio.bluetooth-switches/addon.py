#!/usr/bin/python3
# -*- coding: utf-8 -*-

import json
import os
import re
import subprocess
import sys
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

__PLUGIN_ID__ = "plugin.audio.bluetooth-switches"

SLOTS = 6

SEM6000 = "Voltcraft SEM-6000"
SEM3600BT = "Voltcraft SEM-3600BT"
BS21 = "Renkforce BS-21"

settings = xbmcaddon.Addon(id=__PLUGIN_ID__)
addon_dir = xbmcvfs.translatePath(settings.getAddonInfo('path'))

_autooff = [None, [0, 5], [0, 10], [0, 15], [0, 30], [1, 0], [1, 30], [2, 0]]
_icons = ["icon_bathroom", "icon_bedroom", "icon_bulb", "icon_candle", "icon_coffee",
          "icon_computer", "icon_cooker", "icon_globe", "icon_hall", "icon_kitchen",
          "icon_lamp", "icon_livingroom", "icon_power", "icon_printer", "icon_radio",
          "icon_server", "icon_tv"]
_menu = []


class ContinueLoop(Exception):
    pass


def _exec_bluetoothctl():

    macs = []
    names = []
    models = []

    p1 = subprocess.Popen(["echo", "-e", "select 00:1A:7D:DA:71:13\ndevices\nquit\n\n"],
                          stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["bluetoothctl"], stdin=p1.stdout,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    p1.stdout.close()

    out, err = p2.communicate()

    for match in re.finditer('([0-9A-F:]+) (WiT Power Meter|Voltcraft|BS-21-[0-9]{6}-[01]-A)',
                             out.decode("utf-8")):
        macs += [match.group(1)]
        names += [match.group(2)]

        if match.group(2) == "Voltcraft":
            models += [SEM6000]
        elif match.group(2).startswith("BS-21-"):
            models += [BS21]
        else:
            models += [SEM3600BT]

    return macs, names, models


def discover():

    inserts = []
    free = []

    macs, names, models = _exec_bluetoothctl()

    for m in range(len(macs)):
        try:
            for i in range(SLOTS):
                smac = settings.getSetting("sem_%i_mac" % i)
                senabled = settings.getSetting("sem_%i_enable" % i)
                if smac == macs[m]:
                    raise ContinueLoop

                elif (smac == "" or senabled == "false") and i not in free:
                    free += [i]

            inserts += [m]

        except ContinueLoop:
            continue

    if len(free) == 0 and len(inserts) > 0:
        xbmc.executebuiltin(
            "Notification(All slots are occupied, "
            "Disable a device from list!)")
        return

    for m in inserts:
        slot = None
        if len(free) > 0:
            slot = free.pop(0)
        else:
            continue

        settings.setSetting("sem_%i_mac" % slot, macs[m])
        settings.setSetting("sem_%i_name" % slot, names[m])
        settings.setSetting("sem_%i_model" % slot, models[m])

    if len(macs) == 0:
        xbmc.executebuiltin(
            "Notification(No supported bluetooth switches found, "
            "Check if at least one switch is paired!)")

    elif len(inserts) == 0:
        xbmc.executebuiltin(
            "Notification(No new bluetooth switches found, "
            "Check already paired bluetooth switches!)")
    else:
        xbmc.executebuiltin(
            "Notification(New bluetooth SEM found, "
            "%i new bluetooth switches added to device list)" % len(inserts))


def _get_directory_by_path(path):

    if path == "/":
        return _menu[0]

    tokens = path.split("/")[1:]
    directory = _menu[0]

    while len(tokens) > 0:
        path = tokens.pop(0)
        for node in directory["node"]:
            if node["path"] == path:
                directory = node
                break

    return directory


def _build_param_string(param, values, current=""):

    if values == None:
        return current

    for v in values:
        current += "?" if len(current) == 0 else "&"
        current += param + "=" + str(v)

    return current


def _add_list_item(entry, path):

    if path == "/":
        path = ""

    item_path = path + "/" + entry["path"]
    item_id = item_path.replace("/", "_")

    param_string = ""
    if "send" in entry:
        param_string = _build_param_string(
            param="send",
            values=entry["send"],
            current=param_string)

    if "param" in entry:
        param_string = _build_param_string(
            param=entry["param"][0],
            values=[entry["param"][1]],
            current=param_string)

    if "msg" in entry:
        param_string = _build_param_string(
            param="msg",
            values=[entry["msg"]],
            current=param_string)

    if "node" in entry:
        is_folder = True
    else:
        is_folder = False

    label = entry["name"]
    if settings.getSetting("label%s" % item_id) != "":
        label = settings.getSetting("label%s" % item_id)

    if "icon" in entry:
        icon_file = os.path.join(
            addon_dir, "resources", "assets", entry["icon"] + ".png")
    else:
        icon_file = None

    li = xbmcgui.ListItem(label)
    li.setArt({"icon": icon_file})

    xbmcplugin.addDirectoryItem(handle=addon_handle,
                                listitem=li,
                                url="plugin://" + __PLUGIN_ID__
                                + item_path
                                + param_string,
                                isFolder=is_folder)


def _read_settings(i):

    mac = settings.getSetting("sem_%i_mac" % i)
    alias = settings.getSetting("sem_%i_name" % i)
    enabled = settings.getSetting("sem_%i_enabled" % i)
    icon = settings.getSetting("sem_%i_icon" % i)
    autooff = settings.getSetting("sem_%i_autooff" % i)
    model = settings.getSetting("sem_%i_model" % i)
    pin = settings.getSetting("sem_%i_pin" % i)
    pin = ("0000%s" % pin)[-4:]

    return mac, alias, enabled, icon, autooff, model, pin


def _build_dir_structure(path, url_params):

    global _menu

    splitted_path = path.split("/")
    splitted_path.pop(0)

    entries = []

    for i in range(SLOTS):

        mac, alias, enabled, icon, autooff, model, pin = _read_settings(i)

        if mac == "" or enabled != "true":
            continue

        entries += [
            {
                "path": mac,
                "name": alias,
                "icon": _icons[int(icon)],
                "msg": alias,
                "node": [
                    {
                        "path": "on",
                        "name": "turn on",
                        "icon": _icons[int(icon)],
                        "send": ["%i" % i, "on"],
                        "msg": alias
                    },
                    {
                        "path": "off",
                        "name": "turn off",
                        "icon": _icons[int(icon)],
                        "send": ["%i" % i, "off"],
                        "msg": alias
                    }
                ]
            }
        ]

    _menu = [
        {
            "path": "",
            "node": entries
        }
    ]


def browse(path, url_params):

    _build_dir_structure(path, url_params)

    directory = _get_directory_by_path(path)
    for entry in directory["node"]:
        _add_list_item(entry, path)

    xbmcplugin.endOfDirectory(addon_handle)


def _call_switch(model, mac, pin, command, auto_off):

    if auto_off != None:
        _hh = auto_off[0]
        _mm = auto_off[1]
    else:
        _hh = 0
        _mm = 0

    call = []
    if model == SEM6000:
        call += [addon_dir + os.sep + "lib" +
                 os.sep + "sem-6000.exp", mac, pin, "--sync"]
        call += ["--%s" % command] if command != "" else []
        call += ["--countdown", "off", "+%i" %
                 (_hh * 60 + _mm)] if auto_off != None else []
        call += ["--status", "--json"]

    elif model == SEM3600BT:
        call += [addon_dir + os.sep + "lib" +
                 os.sep + "vc-sem.exp", mac, "--sync"]
        call += ["--%s" % command] if command != "" else []
        call += ["--countdown", "off", "+%i" %
                 (_hh * 60 + _mm)] if auto_off != None else []
        call += ["--status", "--json"]

    else:
        call += [addon_dir + os.sep + "lib" +
                 os.sep + "bs21.py", mac, pin, "--sync"]
        call += ["--%s" % command] if command != "" else []
        call += ["--countdown", "%.2d:%.2d:00" %
                 (_hh, _mm), "off"] if auto_off != None else []
        call += ["--json"]

    xbmc.log(" ".join(call), xbmc.LOGINFO)

    p = subprocess.Popen(call,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

    out, err = p.communicate()
    return out.decode("utf-8")


def execute(path, params):

    if "silent" not in params:
        xbmc.executebuiltin("Notification(%s, %s, %s/icon.png)"
                            % (params["msg"][0], "Sending data to switch...", addon_dir))

    try:
        mac, alias, enabled, icon, autooff, model, pin = _read_settings(
            int(params["send"][0]))
        command = params["send"][1]
        xbmc.log("Bluetooth Switch (%s): %s %s %s " %
                 (model, mac, pin, alias), xbmc.LOGINFO)
        output = _call_switch(model, mac, pin, command, _autooff[int(autooff)])
        status = json.loads(output)

        if model == BS21:
            on = status["status"]["on"]
        else:
            on = status["status"]["power"]

        msg = "Turned " + ("on" if on else "off")
        if "silent" not in params:
            if on and autooff != "0":
                _min = _autooff[int(autooff)][0] * 60 + \
                    _autooff[int(autooff)][1]
                xbmc.executebuiltin("AlarmClock(%s, Notification(%s, %s, %s/resources/assets/%s.png), %d, True)"
                                    % (alias, alias, alias + " is ready", addon_dir, icon, _min))

            xbmc.executebuiltin("Notification(%s, %s, %s/resources/assets/%s.png)"
                                % (alias, msg, addon_dir, icon))

    except Exception as ex:
        xbmc.log("Bluetooth Switch: %s" % str(ex), xbmc.LOGERROR)
        if "silent" not in params:
            xbmc.executebuiltin("Notification(%s, %s, %s/resources/assets/%s.png)"
                                % (alias, "Failed! Try again", addon_dir, icon))


if __name__ == '__main__':

    if sys.argv[1] == "discover":
        discover()
    else:
        addon_handle = int(sys.argv[1])
        path = urllib.parse.urlparse(sys.argv[0]).path
        url_params = urllib.parse.parse_qs(sys.argv[2][1:])

        if "send" in url_params:
            execute(path, url_params)
        else:
            browse(path, url_params)
