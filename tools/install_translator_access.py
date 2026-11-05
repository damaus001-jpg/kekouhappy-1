"""Apply the reviewed two-file bridge integration to the translator source."""
from pathlib import Path
import shutil
import sys

target = Path(sys.argv[1]).resolve()
source = Path(__file__).parent / 'bridge-client' / 'workspace-access.ts'
main = target / 'electron' / 'main.ts'
text = main.read_text(encoding='utf-8-sig')
anchor = "import { appendFile, cp, readdir, readFile, writeFile, mkdir, rename, rm, stat } from 'node:fs/promises';"
hook = "    callback({ requestHeaders });\n  });\n}\n\nasync function prepareAuthorizedRuntime()"
new_hook = """    try {
      callback({ requestHeaders: workspaceAccessHeaders(
        partitionPolicies.get(profile.partition) || profile.platform,
        details.method, details.url, requestHeaders) });
    } catch {
      // A missing/corrupt credential must never downgrade to an unsigned request.
      callback({ cancel: true });
    }
  });
}

async function prepareAuthorizedRuntime()"""
if "from './workspace-access.js'" not in text:
    if text.count(anchor) != 1 or text.count(hook) != 1:
        raise SystemExit('Translator source changed; integration cancelled')
    text = text.replace(anchor, "import { workspaceAccessHeaders } from './workspace-access.js';\n" + anchor, 1).replace(hook,new_hook,1)
    main.write_text(text,encoding='utf-8',newline='')
shutil.copyfile(source,target / 'electron' / 'workspace-access.ts')
print('Translator bridge source installed')
