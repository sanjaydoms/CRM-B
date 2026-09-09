/**
 * The boutique's roles, in one place.
 *
 * Mirrors crm_api.models.Tailor.ROLE_CHOICES and core.modules.PRODUCTION_ROLES,
 * which core/checks.py already asserts against each other. This file exists
 * because the same list was written out three times in the bundle -- App.jsx,
 * the superadmin console and now the staff screen -- and the third copy is
 * where a list like this starts disagreeing with itself.
 *
 * Owner and Designer are not here: neither is a Tailor.ROLE_CHOICES value, and
 * neither is something the staff screen can assign.
 */
export const STAFF_ROLES = [
  { value: 'Tailor', label: 'Stitching Tailor', hint: 'Stitches the garment.' },
  { value: 'Master', label: 'Master Tailor (generalist)', hint: 'Can work on every stage.' },
  { value: 'Maggam Master', label: 'Maggam Master', hint: 'Runs embroidery before stitching.' },
  { value: 'Karigar', label: 'Karigar', hint: 'Handwork on the frame, alongside the Maggam Master.' },
  { value: 'Packaging Staff', label: 'Packaging Staff', hint: 'Packs the garment before dispatch.' },
  { value: 'QC Staff', label: 'QC Staff', hint: 'Runs the quality inspection.' },
];

export const PRODUCTION_ROLES = STAFF_ROLES.map((r) => r.value);

/**
 * Designer sits apart from the list above on purpose.
 *
 * It is not a Tailor.ROLE_CHOICES value and never can be: a designer is a row
 * in design_studio.Designer, its own table with its own endpoint, and a
 * design-only designer has no roster row at all. The staff screen offers it as
 * a choice because that is where a boutique goes to add a person -- but the
 * form posts somewhere else when it is picked, and nothing that reasons about
 * production roles should find it in PRODUCTION_ROLES.
 */
export const DESIGNER_ROLE = {
  value: 'Designer',
  label: 'Designer',
  hint: 'Works in the Design Studio; not on the production floor.',
};

/** What the staff screen's role picker offers. */
export const ASSIGNABLE_ROLES = [...STAFF_ROLES, DESIGNER_ROLE];

/** What a staff document can be. Mirrors StaffDocument.Kind on the server. */
export const DOCUMENT_KINDS = [
  ['AADHAAR', 'Aadhaar'],
  ['PAN', 'PAN card'],
  ['DRIVING_LICENCE', 'Driving licence'],
  ['VOTER_ID', 'Voter ID'],
  ['BANK_PASSBOOK', 'Bank passbook'],
  ['CONTRACT', 'Signed contract'],
  ['CERTIFICATE', 'Certificate'],
  ['OTHER', 'Other'],
];
