/* Minimal role-filtered Desk portal, no external libraries or CDN. */
frappe.pages["administration-v3"].on_page_load = function(wrapper) {
  var page = frappe.ui.make_app_page({parent: wrapper, title: "EuP Administration", single_column: true});
  var root = $('<div class="container-fluid" style="padding:16px"></div>').appendTo(page.body);
  $('<h3></h3>').text("My Requests").appendTo(root);
  var reqs = $('<div class="mb-4"></div>').appendTo(root);
  $('<h3></h3>').text("My Approvals").appendTo(root);
  var approvals = $('<div class="mb-4"></div>').appendTo(root);
  $('<h3></h3>').text("Overview").appendTo(root);
  var overview = $('<div class="mb-4"></div>').appendTo(root);
  page.add_inner_button("New Service Request", function() { frappe.new_doc("ADM General Service Request"); });
  page.add_inner_button("Refresh", load);
  function load() {
    reqs.empty(); approvals.empty(); overview.empty();
    frappe.call({
      method: "eup_administration.v3.registry.my_requests",
      callback: function(r) {
        var rows = r.message || [];
        if (!rows.length) $('<p class="text-muted"></p>').text("No requests found").appendTo(reqs);
        rows.forEach(function(x) {
          var a = $('<a class="list-group-item d-block"></a>').text(
            (x.summary || x.reference_name) + " — " + x.source_status
          );
          a.attr("href", "/app/" + frappe.router.slug(x.reference_doctype) + "/" + encodeURIComponent(x.reference_name));
          reqs.append(a);
        });
      }
    });
    frappe.call({
      method: "eup_administration.v3.approval.pending_for_me",
      callback: function(r) {
        var items = r.message || [];
        if (!items.length) $('<p class="text-muted"></p>').text("No approvals pending").appendTo(approvals);
        items.forEach(function(x) {
          var line = $('<div class="list-group-item"></div>').appendTo(approvals);
          $('<span></span>').text(x.request + " — " + x.department).appendTo(line);
          var btn = $('<button class="btn btn-sm btn-primary ml-2">Approve</button>').appendTo(line);
          btn.on("click", function() {
            frappe.confirm("Approve this request?", function() {
              frappe.call({method:"eup_administration.v3.approval.decide",
                type:"POST",args:{case_id:x.case,decision:"Approved"},
                callback:function(){ load(); }});
            });
          });
        });
      }
    });
    frappe.call({
      method: "eup_administration.v3.reporting.dashboard",
      callback: function(r) {
        var x = r.message || {};
        $('<p></p>').text("Visible requests: " + (x.total || 0) + " | Overdue: " + (x.overdue || 0)).appendTo(overview);
      }
    });
  }
  load();
};
