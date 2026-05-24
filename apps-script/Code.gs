/**
 * Bliss AI — free Google Sheets storage (no paid APIs).
 *
 * Setup:
 * 1. Open your Google Sheet → Extensions → Apps Script
 * 2. Paste this file, save
 * 3. Run setupSheet once (Run menu) and approve permissions
 * 4. Deploy → New deployment → Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 5. Copy the Web App URL into .env (APPS_SCRIPT_URL) and web/config.js
 */

const SHEET_NAME = 'Leads';
const HEADERS = [
  'Timestamp',
  'Source',
  'Contact',
  'Caller Name',
  'Event Type',
  'Requested Date',
];

function setupSheet() {
  const sheet = getOrCreateSheet_();
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
  } else if (sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0].join() !== HEADERS.join()) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  }
}

function doGet(e) {
  const params = e && e.parameter ? e.parameter : {};
  if (params.name || params.eventType || params.date) {
    saveLead_({
      source: params.source || 'web',
      contact: params.contact || '',
      name: params.name || '',
      eventType: params.eventType || '',
      date: params.date || '',
    });
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  return ContentService.createTextOutput('Bliss AI sheet webhook is running.');
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    saveLead_(body);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ ok: false, error: String(err) })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

function saveLead_(data) {
  setupSheet();
  const sheet = getOrCreateSheet_();
  sheet.appendRow([
    new Date(),
    data.source || '',
    data.contact || '',
    data.name || '',
    data.eventType || data.event_type || '',
    data.date || '',
  ]);
}

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  return sheet;
}
