from pathlib import Path
s=Path('probe_native_search_number.py').read_text(encoding='utf-8')
s=s.replace("if any(', Show Conversation Details, Button' in c for c in before):raise RuntimeError('Refusing keyboard navigation in a conversation with possible draft')", "if not any(c.startswith('New Message, Show Conversation Details, Button') for c in before) or 'To:' not in before:raise RuntimeError('New message recipient state not confirmed')")
s=s.replace("if not any(c=='close, Button' for c in before):raise RuntimeError('Search state not confirmed')", "")
s=s.replace("'after_search_number'", "'after_recipient_number'")
Path('probe_native_recipient_number.py').write_text(s,encoding='utf-8')
