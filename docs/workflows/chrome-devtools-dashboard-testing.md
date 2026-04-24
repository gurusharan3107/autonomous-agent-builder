# Chrome DevTools MCP Dashboard Testing Workflow

## Overview
This workflow uses Chrome DevTools MCP to systematically test frontend dashboards by connecting to a running Chrome instance, navigating through pages, and verifying functionality.

## Prerequisites
- Chrome DevTools MCP server configured in `.kiro/settings/mcp.json`
- Chrome browser running with remote debugging enabled
- Dashboard application running on specified port

## MCP Configuration

Add to `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "chrome-devtools-mcp@latest",
        "--autoConnect"
      ]
    }
  }
}
```

## Workflow Steps

### 1. List Available Pages
```
mcp_chrome_devtools_list_pages
```
- Shows all open Chrome tabs
- Identifies the dashboard page by URL
- Note the page ID for selection

### 2. Open or Select Dashboard Page
If dashboard not open:
```
mcp_chrome_devtools_new_page
  url: "http://127.0.0.1:9876"  # builder start default; change only if you passed --port
```

If already open:
```
mcp_chrome_devtools_select_page
  pageId: <id>
  bringToFront: true
```

### 3. Take Initial Snapshot
```
mcp_chrome_devtools_take_snapshot
```
- Captures accessibility tree structure
- Shows all interactive elements with UIDs
- Identifies navigation links and page structure

### 4. Navigate Through Each Page
For each navigation link:
```
mcp_chrome_devtools_click
  uid: <navigation_link_uid>
  includeSnapshot: true
```

### 5. Document Findings
For each page, record:
- Page title and URL
- Main content sections
- Interactive elements
- Data displayed
- Any errors or issues

### 6. Optional: Take Screenshots
```
mcp_chrome_devtools_take_screenshot
  filePath: "screenshots/page-name.png"
```

### 7. Optional: Check Console/Network
```
mcp_chrome_devtools_list_console_messages
mcp_chrome_devtools_list_network_requests
```

## Example: Testing Agent Builder Dashboard

### Pages to Test
1. **Board** - Task pipeline and status
2. **Metrics** - Performance and cost metrics
3. **Knowledge** - Documentation repository
4. **Memory** - Agent learning storage
5. **Setup** - Project configuration

### Test Checklist
- [ ] All navigation links work
- [ ] Page content loads correctly
- [ ] No console errors
- [ ] Data displays properly
- [ ] Interactive elements are accessible
- [ ] Layout renders correctly

## Benefits
- **Automated**: No manual clicking required
- **Systematic**: Ensures all pages are tested
- **Documented**: Snapshots provide evidence
- **Repeatable**: Can be run on every deployment
- **Accessible**: Uses a11y tree for verification

## Common Issues
- **Connection Failed**: Ensure Chrome is running with remote debugging
- **Page Not Found**: Verify dashboard server is running on correct port
- **Timeout**: Increase timeout for slow-loading pages

## Advanced Usage
- Run Lighthouse audits for performance/accessibility
- Capture network requests for API testing
- Execute JavaScript for dynamic testing
- Take memory snapshots for leak detection
