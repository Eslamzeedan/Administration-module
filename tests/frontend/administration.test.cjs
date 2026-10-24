const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const source = p => fs.readFileSync(path.join(root,p),"utf8");
const identity = (text, args=[]) => String(text).replace(/\{(\d+)\}/g,(_,i)=>args[i]??"");
const chain = () => new Proxy({}, {get:(_,name)=>name==="then"?undefined:(...args)=>chain()});

function helper(call) {
    const context = {
        Promise, Intl, console, __:identity,
        document:{documentElement:{lang:"en"},body:{classList:{toggle(){}}}},
        $:()=>chain(), eup_administration:{ui:{}},
        frappe:{provide(){},call,get_route:()=>[],router:{on(){}},set_route(){}}
    };
    vm.runInNewContext(source("eup_administration/public/js/administration_ui.js"),context);
    return context.eup_administration.ui;
}

test("legacy Deferred without finally becomes a native promise",async()=>{
    const deferred={then(resolve){resolve({message:{ok:true}});}};
    assert.equal(deferred.finally,undefined);
    const ui=helper(()=>deferred);
    const promise=ui.call({});
    assert.equal(typeof promise.finally,"function");
    assert.deepEqual(await ui.request("read.method"),{ok:true});
});

test("request rejection propagates and a later request succeeds",async()=>{
    let fail=true, seen=[];
    const ui=helper(options=>{
        seen.push(options);
        return {then(resolve,reject){fail?reject({message:"Denied"}):resolve({message:42});}};
    });
    await assert.rejects(ui.request("write.method",{},"POST"));
    fail=false;
    assert.equal(await ui.request("read.method"),42);
    assert.equal(seen[0].type,"POST");
    assert.equal(seen[1].type,"GET");
});

function workflow(doc, sharedUI = helper(()=>Promise.resolve({}))) {
    const buttons={}, messages=[], prompts=[];
    const context={
        __:identity,
        eup_administration:{ui:sharedUI},
        frappe:{
            ui:{form:{on(_dt,handlers){context.handlers=handlers;}}},
            utils:{escape_html:value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))},
            msgprint:message=>messages.push(message),
            show_alert(){},
            prompt(fields,callback){prompts.push({fields,callback});},
            model:{async set_value(_dt,name,field,value){doc.transitions.find(r=>r.name===name)[field]=value;}}
        }
    };
    vm.runInNewContext(source("eup_administration/eup_administration/doctype/adm_workflow_policy/adm_workflow_policy.js"),context);
    const frm={doc,is_new:()=>true,set_intro(){},
        add_custom_button(label,fn){buttons[label]=fn;},
        clear_table(table){doc[table]=[];},
        async set_value(field,value){doc[field]=value;},
        add_child(table,row){const record={name:table+"-"+doc[table].length,...row};doc[table].push(record);return record;},
        refresh_fields(){},dirty(){}};
    context.handlers.refresh(frm);
    return {buttons,messages,prompts};
}

test("template replaces all auto-created blank grid rows",async()=>{
    const doc={states:[{state:"",sla_hours:0}],transitions:[{conditions:"[]",approval_required:0}],approval_bands:[{}]};
    const w=workflow(doc);
    await w.buttons["Load review template"]();
    assert.deepEqual(doc.states.map(r=>r.state),["Draft","Review","Completed"]);
    assert.deepEqual(doc.transitions.map(r=>r.action),["Submit","Complete"]);
    assert.equal(doc.approval_bands.length,1);
    assert.equal(doc.initial_state,"Draft");
    w.buttons["Preview flow"]();
    assert.equal(w.messages.length,1);
    assert.ok(w.messages[0].message.includes("Draft → Review"));
    assert.ok(!w.messages[0].message.includes("→ :"));
});

test("template preserves configured data and cannot append duplicate templates",async()=>{
    const doc={states:[],transitions:[],approval_bands:[]};
    const w=workflow(doc);
    await w.buttons["Load review template"]();
    const before=JSON.stringify(doc);
    await w.buttons["Load review template"]();
    assert.equal(JSON.stringify(doc),before);
    assert.match(w.messages[0],/empty draft/);
});

test("condition builder omits unnamed actions and rejects non-array JSON",async()=>{
    const doc={states:[],transitions:[{}, {name:"T1",action:"Submit",conditions:"{}"}],approval_bands:[]};
    const w=workflow(doc);
    w.buttons["Add condition"]();
    assert.equal(w.prompts[0].fields[0].options,"Submit");
    await w.prompts[0].callback({action:"Submit",field:"priority",op:"eq",value:"High"});
    assert.equal(doc.transitions[1].conditions,"{}");
    assert.match(w.messages[0],/JSON list/);
    doc.transitions[1].conditions="[]";
    await w.prompts[0].callback({action:"Submit",field:"priority",op:"eq",value:"High"});
    assert.deepEqual(JSON.parse(doc.transitions[1].conditions),[{field:"priority",op:"eq",value:"High"}]);
});

test("preview escapes user text and rejects incomplete transitions",()=>{
    const doc={states:[{state:"<img onerror=alert(1)>"}],transitions:[{action:"Submit"}],approval_bands:[]};
    const w=workflow(doc);
    w.buttons["Preview flow"]();
    assert.match(w.messages[0],/Complete the action/);
    doc.transitions[0]={action:"Submit",from_state:"<img>",to_state:"Done",allowed_role:"Role"};
    w.buttons["Preview flow"]();
    assert.ok(w.messages[1].message.includes("&lt;img"));
    assert.ok(!w.messages[1].message.includes("<img"));
});

function commandCenter(request) {
    const states=[],metrics=[],fields={};
    let primary;
    const ui={
        request,hero(){},action(){},open(){},bars(){},row(){},
        message:()=> "Access denied",
        state(_target,title,body,kind,retry){states.push({title,body,kind,retry});},
        section:()=>chain(),metric(_root,label,value){metrics.push({label,value});}
    };
    const page={
        main:{}, add_field(df){
            const field={value:df.fieldname==="company"?"Fixture":df.default,
                get_value(){return this.value;},async set_value(value){this.value=value;}};
            fields[df.fieldname]=field;return field;
        },
        set_primary_action(_label,action){primary=action;},
        add_menu_item(){}
    };
    const context={Promise, console, __:identity, $:()=>chain(), eup_administration:{ui},
        frappe:{pages:{"administration-command-center":{}},ui:{make_app_page:()=>page},
            datetime:{get_today:()=>"2026-10-23",add_days:()=>"2026-10-17"},
            set_route(){},prompt(){},msgprint(){}},window:{location:{}}};
    vm.runInNewContext(source("eup_administration/eup_administration/page/administration_command_center/administration_command_center.js"),context);
    context.frappe.pages["administration-command-center"].on_page_load({});
    return {states,metrics,fields,refresh:()=>primary()};
}

test("Refresh stays promise-compatible and can recover after a denied request",async()=>{
    let fail=true;
    const data={visible_counts:{"ADM Facility Ticket":2},from_date:"2026-10-17",to_date:"2026-10-23",
        contract_notices:[],preventive_due:[],overdue:0,satisfaction:{average:null,responses:0},
        records:[],priorities:{Normal:2},facility_categories:{},incident_categories:{},unresolved_root_causes:0};
    const center=commandCenter(async method=>{
        if(method.endsWith(".context"))return {requires_employee:false,can_choose_company:true};
        if(fail)throw new Error("denied");return data;
    });
    const pending=center.refresh();
    assert.equal(typeof pending.finally,"function");
    await pending;
    assert.equal(center.states.at(-1).kind,"error");
    fail=false;
    await center.refresh();
    assert.ok(center.metrics.some(m=>m.label==="Visible operations"&&m.value===2));
    assert.ok(center.metrics.some(m=>m.label==="Service rating"&&m.value===null));
});

test("missing employee is explained without querying company data",async()=>{
    let reads=0;
    const center=commandCenter(async method=>{
        if(method.endsWith(".context"))return {requires_employee:true};
        reads++;return {};
    });
    await center.refresh();
    assert.equal(reads,0);
    assert.equal(center.states.at(-1).title,"Connect your employee profile");
});


test("portal request links navigate to Desk without depending on the Desk router",()=>{
    const navigations=[], routes=[];
    const context={Promise,Intl,console, __:identity, $:()=>chain(),
        document:{documentElement:{lang:"en"},body:{classList:{toggle(){}}}},
        window:{location:{assign:url=>navigations.push(url)}},
        eup_administration:{ui:{}},frappe:{provide(){},call(){}}};
    vm.runInNewContext(source("eup_administration/public/js/administration_ui.js"),context);
    const ui=context.eup_administration.ui;
    ui.open("ADM Facility Ticket","TICKET/a?b#c");
    ui.open("ADM Equipment Booking");
    assert.deepEqual(navigations,["/desk/adm-facility-ticket/TICKET%2Fa%3Fb%23c","/desk/adm-equipment-booking"]);
    context.frappe.router={on(){}};
    context.frappe.set_route=(...args)=>routes.push(args);
    ui.open("ADM Facility Ticket","FAC-00001");
    assert.deepEqual(routes,[["Form","ADM Facility Ticket","FAC-00001"]]);
    assert.equal(navigations.length,2);
});


test("refresh replaces only the administration intro and preserves other warnings",()=>{
    const external={classes:["form-message"],text:"Permission warning"};
    const container={rows:[external],children(selector){
        const found=this.rows.filter(row=>row.classes.includes(selector.slice(1)));
        return {remove:()=>{this.rows=this.rows.filter(row=>!found.includes(row));},
            last:()=>({addClass:name=>found.at(-1)?.classes.push(name)})};
    }};
    const frm={layout:{message:container},set_intro(text,color){
        container.rows.push({classes:["form-message"],text,color});
    }};
    const ui=helper(()=>{});
    ui.intro(frm,"Old workflow guidance");
    ui.intro(frm,"Current workflow guidance","yellow");
    assert.equal(container.rows.length,2);
    assert.equal(container.rows[0],external);
    assert.equal(container.rows[1].text,"Current workflow guidance");
    assert.equal(container.rows[1].color,"yellow");
    ui.intro(frm);
    assert.deepEqual(container.rows,[external]);
});


test("shared UI boots before the first route and follows later router changes",()=>{
    let route=null, changed;
    const classes=[];
    const context={Promise,Intl,console,__ :identity,eup_administration:{ui:{}},
        document:{documentElement:{lang:"en"},body:{classList:{toggle:(name,on)=>classes.push({name,on})}}},
        $:value=>typeof value==="function"?value():{on(){}},
        frappe:{provide(){},get_route:()=>route,router:{on(event,callback){assert.equal(event,"change");changed=callback;}}}};
    assert.doesNotThrow(()=>vm.runInNewContext(source("eup_administration/public/js/administration_ui.js"),context));
    assert.equal(typeof changed,"function");
    assert.equal(classes.at(-1).on,false);
    route=["Form","ADM Facility Ticket","QA-1"];changed();
    assert.equal(classes.at(-1).on,true);
    route=["List","User"];changed();assert.equal(classes.at(-1).on,false);
    for(route of [undefined,null,"Form/ADM Facility Ticket"])assert.doesNotThrow(changed);
});

test("workflow designer remains usable in a tab with the preceding shared asset",()=>{
    const w=workflow({states:[],transitions:[],approval_bands:[]},{});
    assert.equal(typeof w.buttons["Load review template"],"function");
    w.buttons["Preview flow"]();
    assert.match(w.messages[0],/Add at least one named state/);
});

test("all operation forms tolerate an already-open tab without the new intro helper",async()=>{
    const doctypes=["adm_facility_ticket","adm_driver_checklist","adm_preventive_plan","adm_parcel",
        "adm_equipment_booking","adm_contract_register","adm_operational_incident","adm_recurring_task","adm_task_occurrence"];
    for(const dt of doctypes){
        const refreshers=[],messages=[];
        const context={__:identity,eup_administration:{ui:{request:async()=>({requires_employee:true})}},
            frappe:{ui:{form:{on(_name,handlers){refreshers.push(handlers.refresh);}}}}};
        vm.runInNewContext(source("eup_administration/eup_administration/doctype/"+dt+"/"+dt+".js"),context);
        const frm={is_new:()=>true,doc:{},set_intro:message=>messages.push(message)};
        assert.doesNotThrow(()=>refreshers[0](frm),dt);
        await Promise.resolve();await Promise.resolve();
        assert.equal(messages.length,1,dt);
        assert.match(messages[0],/active employee/,dt);
    }
});
