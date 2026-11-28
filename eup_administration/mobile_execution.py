"""Stage mobile execution backed by existing driver/runner transitions."""
import base64
from hashlib import sha256
from io import BytesIO

import frappe
from PIL import Image
from frappe.utils.file_manager import save_file
from eup_administration import runner, trip_portal
from eup_administration.mobile_work import SPECS, TRIP, ERRAND

MAX_BYTES = 8 * 1024 * 1024

@frappe.whitelist(methods=["GET"])
def task(kind, name):
    if kind not in SPECS:
        frappe.throw("Unsupported task")
    doc = frappe.get_doc(kind, name)
    doc.check_permission("read")
    doc.apply_fieldlevel_read_permissions()
    result = {"name":name,"kind":kind,"status":doc.status,"purpose":doc.get(SPECS[kind][1])}
    if kind == TRIP:
        result.update(trip_portal.serialize(doc))
    if kind == ERRAND:
        result.update(location=doc.service_location, due=doc.needed_by, rides=len(doc.get("rides") or []),
                      total=doc.actual_transport_cost, currency=doc.currency,
                      assigned=doc.assigned_runner == frappe.session.user and runner.valid_runner(frappe.session.user))
    # The source read check gates this projection; only time and status are returned.
    rows = frappe.get_all("ADM Request Event", filters={"reference_doctype":kind,"reference_name":name},
                          fields=["occurred_at as at","new_status as state"],order_by="occurred_at asc, name asc",limit_page_length=0)
    events = [{"at":doc.creation,"state":"Created"}]
    events.extend(dict(at=r.at,state=r.state) for r in rows if r.state and r.at)
    if kind == TRIP:
        for stop in doc.get("stops") or []:
            for key, state in (("arrived_at","Stop arrival"),("departed_at","Stop departure")):
                if stop.get(key):
                    events.append(dict(at=stop.get(key),state=state,place=stop.location))
        if doc.destination_arrived_at and not doc.get("stops"):
            events.append(dict(at=doc.destination_arrived_at,state="Destination arrival"))
        for key,state in (("actual_start","In Progress"),("actual_end","Completed")):
            if doc.get(key) and not any(e["state"]==state for e in events):
                events.append(dict(at=doc.get(key),state=state))
    result["events"]=sorted(events,key=lambda e:str(e["at"]))
    return result

def receipt_content(encoded):
    if not isinstance(encoded,str) or len(encoded)>4*((MAX_BYTES+2)//3):
        frappe.throw("Image exceeds 8 MB")
    try:
        raw=base64.b64decode(encoded,validate=True)
        with Image.open(BytesIO(raw)) as img:
            if img.format not in {"JPEG","PNG"} or img.width*img.height>50_000_000:
                raise ValueError()
            extension=img.format.lower()
            img.verify()
    except (ValueError,OSError,Image.DecompressionBombError):
        frappe.throw("Select a valid JPEG or PNG image")
    return raw,extension

@frappe.whitelist(methods=["POST"])
def evidence(name, action, image, pickup="", dropoff="", ridden_at="", fare=None, notes=""):
    doc=runner._load(name)
    doc.check_permission("read")
    runner._runner(doc)
    if action not in ("ride","complete"):
        frappe.throw("Invalid action")
    raw,ext=receipt_content(image)
    digest=sha256(raw).hexdigest()
    ref="MOB-"+digest
    if action=="ride":
        for row in doc.get("rides") or []:
            if row.booking_reference==ref:
                from frappe.utils import get_datetime
                if (row.pickup!=pickup.strip() or row.dropoff!=dropoff.strip()
                        or get_datetime(row.ridden_at)!=get_datetime(ridden_at) or runner.money(row.fare)!=runner.money(fare)):
                    frappe.throw("This receipt was already recorded with different details")
                return {"name":name,"status":doc.status}
    elif doc.status in {"Completed","Closed"} and doc.completion_notes==notes.strip() and doc.completion_proof:
        # A mission has one immutable completion; return the proof already accepted.
        return {"name":name,"status":doc.status,"proof":doc.completion_proof,"already_completed":True}
    runner._require_status(doc,"In Progress")
    file=save_file(action+"-"+digest[:24]+"."+ext,raw,ERRAND,name,is_private=1)
    if action=="ride":
        return runner.add_careem_ride(name,pickup,dropoff,ridden_at,fare,file.file_url,ref)
    return runner.complete_errand(name,file.file_url,notes)
