frappe.ready(function() {
    const ui = eup_administration.ui;
    const api = "eup_administration.v4.";
    const root = document.querySelector(".adm-self-service");
    const list = $("#adm-portal-list"), status = $("#adm-portal-status");
    const refreshButton = document.getElementById("adm-refresh"), newButton = document.getElementById("adm-new-request");
    let home, generation = 0, loading = false;
    function promptFields(fields, submit) {
        const dialog = document.createElement("dialog");
        dialog.className = "adm-dialog adm-self-service";
        dialog.setAttribute("aria-label", __("Administration request"));
        const heading = document.createElement("h2"); heading.textContent = __("Request details");
        const form = document.createElement("form"), errors = document.createElement("div");
        errors.setAttribute("role","alert"); errors.className="adm-note";
        for (const field of fields) {
            const label = document.createElement("label"); label.textContent=field.label;
            const input = document.createElement(field.fieldtype==="Select" ? "select" : field.fieldtype==="Small Text" ? "textarea" : "input");
            input.className="form-control"; input.name=field.fieldname; input.required=!!field.reqd;
            input.id="adm-input-"+field.fieldname; label.htmlFor=input.id;
            if (field.fieldtype==="Datetime") input.type="datetime-local";
            if (field.fieldtype==="Select") for (const value of (field.options||"").split("\n").filter(Boolean)) {
                const option=document.createElement("option"); option.value=value; option.textContent=value; input.appendChild(option);
            }
            input.value=field.default||input.value||"";
            label.appendChild(input); form.appendChild(label);
        }
        const actions=document.createElement("div"); actions.className="adm-toolbar";
        const save=document.createElement("button"); save.type="submit"; save.className="btn btn-primary"; save.textContent=__("Continue");
        const cancel=document.createElement("button"); cancel.type="button"; cancel.className="btn btn-default"; cancel.textContent=__("Cancel");
        cancel.onclick=()=>dialog.close(); actions.append(save,cancel);
        form.append(errors,actions);
        form.onsubmit=async event=>{
            event.preventDefault();
            if (save.disabled) return;
            save.disabled=true; cancel.disabled=true; errors.textContent=__("Please wait…");
            try {
                await submit(Object.fromEntries(new FormData(form).entries()));
                dialog.close();
            } catch(error) {
                errors.textContent=ui.message(error);
                save.disabled=false; cancel.disabled=false;
            }
        };
        dialog.append(heading,form); document.body.appendChild(dialog);
        dialog.addEventListener("cancel",event=>{if(save.disabled)event.preventDefault();});
        dialog.addEventListener("close",()=>dialog.remove(),{once:true});
        dialog.showModal();
    }
    function button(parent,label,action,primary=false) {
        const b=document.createElement("button"); b.type="button";
        b.className=primary?"btn btn-primary":"btn btn-default"; b.textContent=label;
        b.onclick=async()=>{
            b.disabled=true;
            try { await action(); } catch(error) { frappe.msgprint(ui.message(error)); }
            finally { b.disabled=false; }
        };
        parent.appendChild(b); return b;
    }
    async function mutate(method,args) {
        await ui.request(api+method,args,"POST");
        await refresh();
    }
    async function refresh() {
        if(root.dataset.employeeReady!=="1") {
            newButton.disabled=true;
            ui.state(status,__("Connect your employee profile"),
                __("Ask your administrator to link your login to an active employee in your company. Your service requests will appear here once that is complete."));
            return;
        }
        if(loading)return;
        loading=true; refreshButton.disabled=true; newButton.disabled=true;
        const ticket=++generation;
        ui.state(status,__("Loading your requests"),__("Checking the latest progress."),"loading");
        try {
            home=await ui.request(api+"portal.home");
            if(ticket!==generation)return;
            list.empty(); status.empty();
            $("<p class='adm-note'></p>").text(__("Showing your visible requests for the last seven days. Open the administration workspace for older requests.")).appendTo(status);
            if(!home.records.length)ui.state(status,__("No requests yet"),__("Choose New request to get started."));
            for(const row of home.records) {
                const card=$('<article class="adm-portal-card"></article>').appendTo(list);
                $("<h3></h3>").text(row.subject).appendTo(card);
                card.append(ui.badge(row.workflow_state||__("Draft")));
                $("<p class='adm-note'></p>").text(__(row.doctype.replace("ADM ",""))+" · "+row.name).appendTo(card);
                const actions=$('<div class="adm-toolbar"></div>').appendTo(card)[0];
                button(actions,__("Open request"),()=>ui.open(row.doctype,row.name));
                ui.request(api+"workflow.available",{doctype:row.doctype,name:row.name}).then(info=>{
                    if(ticket!==generation)return;
                    for(const action of info.actions||[])button(actions,__(action),()=>mutate("workflow.transition",{
                        doctype:row.doctype,name:row.name,action,expected_revision:info.revision
                    }),true);
                    if(info.can_feedback)button(actions,__("Rate service"),()=>promptFields([
                        {fieldname:"rating",fieldtype:"Select",options:"5\n4\n3\n2\n1",label:__("Rating out of 5"),reqd:1},
                        {fieldname:"comment",fieldtype:"Small Text",label:__("Comment")}
                    ],async values=>{
                        await ui.request(api+"operations.feedback",{doctype:row.doctype,name:row.name,...values},"POST");
                        frappe.show_alert({message:__("Thank you for your feedback."),indicator:"green"});
                        await refresh();
                    }));
                    if(info.can_acknowledge)button(actions,__("Acknowledge receipt"),()=>mutate("operations.acknowledge_parcel",{name:row.name}));
                    if(info.can_release)button(actions,__("Release booking"),()=>mutate("operations.release_booking",{name:row.name}));
                }).catch(()=>{
                    $("<p class='adm-note'></p>").text(__("Actions couldn't be loaded. Refresh to try again.")).appendTo(card);
                });
            }
        } catch(error) { ui.state(status,__("Requests couldn't be loaded"),ui.message(error),"error",refresh); }
        finally { loading=false; refreshButton.disabled=false; newButton.disabled=!home; }
    }
    refreshButton.addEventListener("click",refresh);
    newButton.addEventListener("click",()=>{
        if(!home)return;
        promptFields([{fieldname:"doctype",fieldtype:"Select",options:"ADM Facility Ticket\nADM Parcel\nADM Equipment Booking",label:__("Request type"),reqd:1}],async selected=>{
            const type=selected.doctype, policies=home.policies.filter(p=>p.target_doctype===type);
            if(!policies.length)throw new Error(__("No enabled workflow is configured for this request type. Ask your administration team to configure one."));
            const fields=[
                {fieldname:"subject",fieldtype:"Data",label:__("Subject"),reqd:1},
                {fieldname:"description",fieldtype:"Small Text",label:__("Details")},
                {fieldname:"priority",fieldtype:"Select",options:"Low\nNormal\nHigh\nCritical",default:"Normal",label:__("Priority")},
                {fieldname:"policy_name",fieldtype:"Select",options:policies.map(p=>p.name).join("\n"),label:__("Workflow"),reqd:1}
            ];
            if(type==="ADM Facility Ticket")fields.push(
                {fieldname:"location",fieldtype:"Data",label:__("Location"),reqd:1},
                {fieldname:"category",fieldtype:"Select",options:"Electrical\nPlumbing\nCleaning\nSafety\nOther",label:__("Category")});
            if(type==="ADM Parcel")fields.push(
                {fieldname:"tracking_number",fieldtype:"Data",label:__("Tracking number"),reqd:1},
                {fieldname:"sender",fieldtype:"Data",label:__("Sender"),reqd:1},
                {fieldname:"recipient",fieldtype:"Link",label:__("Recipient login"),reqd:1});
            if(type==="ADM Equipment Booking")fields.push(
                {fieldname:"equipment",fieldtype:"Select",options:home.equipment.map(e=>e.name).join("\n"),label:__("Equipment"),reqd:1},
                {fieldname:"starts_at",fieldtype:"Datetime",label:__("Start"),reqd:1},
                {fieldname:"ends_at",fieldtype:"Datetime",label:__("End"),reqd:1});
            promptFields(fields,async values=>{
                const policy_name=values.policy_name; delete values.policy_name;
                // datetime-local is a user's local value; retain it for Frappe's configured site time zone.
                for(const field of ["starts_at","ends_at"])if(values[field])values[field]=values[field].replace("T"," ")+ (values[field].length===16?":00":"");
                await ui.request(api+"portal.create_request",{doctype:type,values,policy_name},"POST");
                await refresh();
            });
        });
    });
    refresh();
});
