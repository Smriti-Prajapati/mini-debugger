import compiler

# Simulate what Monaco sends — \r\n line endings (Windows)
source_crlf = "#include <iostream>\r\nusing namespace std;\r\n\r\nint main() {\r\n    int x = 5\r\n    int y = 10;\r\n    return 0;\r\n}\r\n"

print("Testing with CRLF line endings:")
print("Line 5 bytes:", repr(source_crlf.split('\r\n')[4]))
r = compiler.compile_source(source_crlf)
print("raw:", r['raw_output'])
print("parsed:", r['errors'])
compiler.cleanup_work_dir(r['work_dir'])
