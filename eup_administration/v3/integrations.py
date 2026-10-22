"""Read-only HRMS integration and guarded external-service metadata."""
from urllib.parse import urlparse
import frappe
from eup_administration.v3.security import active_employee


@frappe.whitelist()
def my_employee():
    e = active_employee()
    if not e:
        return None
    return {"employee": e.name, "company": e.company, "department": e.department}


def nextcloud_safe_link(url):
    if not frappe.db.get_single_value("ADM Settings", "enable_nextcloud_links"):
        frappe.throw("Nextcloud links are disabled")
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or parsed.hostname != "cloud.eupegypt.com":
        frappe.throw("Only the configured company Nextcloud host is allowed")
    if parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
        frappe.throw("Unsafe external URL")
    if any(key.lower() in {"token", "password", "auth", "access_token"} for key in [x.split("=")[0] for x in parsed.query.split("&")]):
        frappe.throw("Do not store Nextcloud share tokens in link fields")
    return url
