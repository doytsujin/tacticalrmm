from time import sleep

from agents.models import Agent
from .models import WinUpdate
from tacticalrmm.celery import app


@app.task
def check_for_updates_task(pk, wait=False):
    
    if wait:
        sleep(70)

    agent = Agent.objects.get(pk=pk)

    resp = agent.salt_api_cmd(
        hostname=agent.salt_id,
        timeout=310,
        salt_timeout=300,
        func="win_wua.list",
        arg="skip_installed=False",
    )
    data = resp.json()
    ret = data["return"][0][agent.salt_id]

    # if managed by wsus, nothing we can do until salt supports it
    if type(ret) is str:
        err = ["unknown failure", "2147352567", "2145107934"]
        if any(x in ret.lower() for x in err):
            agent.managed_by_wsus = True
            agent.save(update_fields=["managed_by_wsus"])
            return f"{agent.hostname} managed by wsus"
    else:
        # if previously managed by wsus but no longer (i.e moved into a different OU in AD)
        # then we can use salt to manage updates
        if agent.managed_by_wsus and type(ret) is dict:
            agent.managed_by_wsus = False
            agent.save(update_fields=["managed_by_wsus"])

    guids = []
    for k in ret.keys():
        guids.append(k)

    if not WinUpdate.objects.filter(agent=agent).exists():

        for i in guids:
            WinUpdate(
                agent=agent,
                guid=i,
                kb=ret[i]["KBs"][0],
                mandatory=ret[i]["Mandatory"],
                title=ret[i]["Title"],
                needs_reboot=ret[i]["NeedsReboot"],
                installed=ret[i]["Installed"],
                downloaded=ret[i]["Downloaded"],
                description=ret[i]["Description"],
                severity=ret[i]["Severity"],
            ).save()
    else:
        for i in guids:
            # check if existing update install / download status has changed
            if WinUpdate.objects.filter(agent=agent).filter(guid=i).exists():

                update = WinUpdate.objects.filter(agent=agent).get(guid=i)

                if ret[i]["Installed"] != update.installed:
                    update.installed = not update.installed
                    update.save(update_fields=["installed"])

                if ret[i]["Downloaded"] != update.downloaded:
                    update.downloaded = not update.downloaded
                    update.save(update_fields=["downloaded"])

            # otherwise it's a new update
            else:
                WinUpdate(
                    agent=agent,
                    guid=i,
                    kb=ret[i]["KBs"][0],
                    mandatory=ret[i]["Mandatory"],
                    title=ret[i]["Title"],
                    needs_reboot=ret[i]["NeedsReboot"],
                    installed=ret[i]["Installed"],
                    downloaded=ret[i]["Downloaded"],
                    description=ret[i]["Description"],
                    severity=ret[i]["Severity"],
                ).save()
    return "ok"
