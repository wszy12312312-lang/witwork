const fs = require('fs');
const path = require('path');
const NM = 'C:\\Users\\wszy1\\WorkBuddy\\2026-09-18-01-07-46\\inkrealm\\desktop\\node_modules';
const EMPTY = 'C:\\Users\\wszy1\\WorkBuddy\\2026-09-18-01-07-46\\inkrealm\\desktop\\_empty';
function rm(p) {
  try {
    if (fs.existsSync(p)) {
      fs.rmSync(p, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      console.log('removed', p);
    } else {
      console.log('absent', p);
    }
  } catch (e) {
    console.log('FAIL', p, String(e).slice(0, 200));
  }
}
rm(NM);
rm(EMPTY);
console.log('done');
