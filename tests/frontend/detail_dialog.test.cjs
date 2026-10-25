const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const forms = [
  { slug: 'adm_facility_ticket', doctype: 'ADM Facility Ticket', fields: ['resolution'] },
  { slug: 'adm_parcel', doctype: 'ADM Parcel', fields: ['delivery_note'] },
  { slug: 'adm_operational_incident', doctype: 'ADM Operational Incident', fields: ['root_cause', 'corrective_action'] },
];

function setup(spec, reject = false) {
  const handlers = [], buttons = {}, calls = [], prompts = [];
  let reloads = 0;
  const doc = { name: 'SYNTHETIC-QA', company: 'Test Company', workflow_policy: 'POLICY' };
  for (const field of spec.fields) doc[field] = 'Existing ' + field;
  const frm = { doc, doctype: spec.doctype, is_new: () => false, set_intro() {},
    add_custom_button(label, action) { buttons[label] = action; },
    reload_doc() { reloads++; return Promise.resolve(); } };
  const context = {
    __: text => text,
    eup_administration: { ui: { call(options) {
      if (options.method.endsWith('workflow.available')) return Promise.resolve({ message: {} });
      calls.push(options);
      return reject ? Promise.reject(new Error('Access denied')) : Promise.resolve({ message: {} });
    } } },
    frappe: { session: { user: 'qa' },
      ui: { form: { on(_doctype, events) { handlers.push(events.refresh); } } },
      prompt(fields, callback) { prompts.push({ fields, callback }); } },
  };
  const file = path.join(root, 'eup_administration/eup_administration/doctype', spec.slug, spec.slug + '.js');
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
  for (const refresh of handlers) refresh(frm);
  buttons['Update operational details']();
  return { doc, prompt: prompts[0], calls, reloads: () => reloads };
}

test('optional detail dialogs prefill saved values and post only their permitted fields', async () => {
  for (const spec of forms) {
    const h = setup(spec);
    for (const field of h.prompt.fields) assert.equal(field.default, h.doc[field.fieldname]);
    const values = Object.fromEntries(spec.fields.map(name => [name, 'Updated ' + name]));
    await h.prompt.callback({ ...values, company: 'FORGED' });
    const call = h.calls[0];
    assert.equal(call.method, 'eup_administration.v4.operations.update_details');
    assert.equal(call.type, 'POST');
    assert.equal(call.args.doctype, spec.doctype);
    assert.equal(call.args.name, h.doc.name);
    assert.deepEqual(JSON.parse(JSON.stringify(call.args.values)), values);
    assert.equal(h.reloads(), 1);
  }
});

test('an empty Frappe prompt payload sends explicit blanks through the protected endpoint', async () => {
  for (const spec of forms) {
    const h = setup(spec);
    await h.prompt.callback({}); // Frappe omits empty optional controls.
    assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].args.values)),
      Object.fromEntries(spec.fields.map(name => [name, ''])));
    assert.equal(h.reloads(), 1);
  }
});

test('incident dialog retains the other prefilled value when one field is edited', async () => {
  const h = setup(forms[2]);
  const values = Object.fromEntries(h.prompt.fields.map(field => [field.fieldname, field.default]));
  values.root_cause = 'Revised root cause';
  await h.prompt.callback(values);
  assert.equal(h.calls[0].args.values.corrective_action, 'Existing corrective_action');
  assert.equal(h.calls[0].args.values.root_cause, 'Revised root cause');
});

test('denied detail writes stay rejected and do not pretend that the form reloaded', async () => {
  for (const spec of forms) {
    const h = setup(spec, true);
    await assert.rejects(h.prompt.callback({}), /Access denied/);
    assert.equal(h.reloads(), 0);
  }
});
