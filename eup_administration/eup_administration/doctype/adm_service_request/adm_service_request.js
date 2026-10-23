// Runner/Careem request actions. Careem journeys are separate from ADM Trip.
frappe.ui.form.on('ADM Service Request', {
  refresh(frm) {
    if (frm.is_new()) return;
    eup_administration.ui.call({method:'eup_administration.runner.capabilities', args:{name:frm.doc.name}})
      .then(({message: c}) => {
        if (!c) return;
        const actions = [
          ['submit','Submit Request','submit_request'],
          ['approve','Approve','approve_request'],
          ['reject','Reject','reject_request'],
          ['assign','Assign Runner','assign_runner'],
          ['start','Start Errand','start_errand'],
          ['add_ride','Add Careem Ride','add_careem_ride'],
          ['complete','Complete Errand','complete_errand'],
          ['close','Verify & Close','close_errand'],
          ['cancel','Cancel Request','cancel_request'],
        ];
        actions.forEach(([cap, label, method]) => {
          if (!c[cap]) return;
          frm.add_custom_button(__(label), () => {
            if (method === 'assign_runner') {
              frappe.prompt([{fieldname:'runner', label:'Runner User', fieldtype:'Link', options:'User', reqd:1}],
                values => invoke(frm,method,values),__('Assign Runner'));
            } else if (method === 'reject_request') {
              frappe.prompt([{fieldname:'reason', label:'Rejection Reason', fieldtype:'Small Text', reqd:1}],
                values => invoke(frm,method,values),__('Reject Request'));
            } else if (method === 'add_careem_ride') {
              frappe.prompt([
                {fieldname:'pickup',label:'Pickup',fieldtype:'Data',reqd:1},
                {fieldname:'dropoff',label:'Drop-off',fieldtype:'Data',reqd:1},
                {fieldname:'ridden_at',label:'Ride Time',fieldtype:'Datetime',reqd:1},
                {fieldname:'fare',label:'Actual Fare (EGP)',fieldtype:'Currency',reqd:1},
                {fieldname:'booking_reference',label:'Careem Reference',fieldtype:'Data'},
                {fieldname:'receipt',label:'Private Ride Receipt',fieldtype:'Attach',reqd:1,
                 description:__('Choose Private when uploading. Public receipts are rejected.')},
              ], values => invoke(frm,method,values),__('Add Careem Ride'));
            } else if (method === 'complete_errand') {
              frappe.prompt([
                {fieldname:'proof',label:'Private Completion Proof',fieldtype:'Attach',reqd:1,
                 description:__('Upload as Private. The server rejects public files.')},
                {fieldname:'notes',label:'Completion Notes',fieldtype:'Small Text',reqd:1},
              ], values => invoke(frm,method,values),__('Complete Errand'));
            } else if (method === 'cancel_request') {
              frappe.confirm(__('Cancel this request?'), () => invoke(frm,method,{}));
            } else invoke(frm,method,{});
          }, __('Workflow'));
        });
      });
  }
});
function invoke(frm, method, values) {
  return eup_administration.ui.call({method:`eup_administration.runner.${method}`,type:'POST',
    args:{name:frm.doc.name,...values},freeze:true}).then(() => frm.reload_doc());
}
