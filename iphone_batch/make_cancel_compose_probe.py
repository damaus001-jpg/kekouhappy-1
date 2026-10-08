from pathlib import Path
s=Path('probe_native_recipient_confirm.py').read_text(encoding='utf-8')
s=s.replace("if not any(c.startswith('New Message, Show Conversation Details, Button') for c in before):raise RuntimeError('Recipient entry page not confirmed')", "if not any(c.startswith('New iMessage, Show Conversation Details, Button') for c in before):raise RuntimeError('Expected empty new conversation not confirmed')")
s=s.replace("if 'To:, 9032619764' not in before or 'Message' not in before:raise RuntimeError('Exact recipient or empty composer not confirmed')", "if 'Message, iMessage' not in before:raise RuntimeError('Empty composer not confirmed')")
s=s.replace('([],[0x28],[])','([],[0x29],[])').replace("'after_confirm_recipient'", "'after_escape_empty_compose'")
Path('probe_native_cancel_empty_compose.py').write_text(s,encoding='utf-8')
