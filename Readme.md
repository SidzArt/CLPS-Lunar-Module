Local Test Admin Account (Super Admin)
Username / User ID: test_super_admin
Password: TestAdminPass123!
Role: super_admin (Full access to Site Editor, Media Management, Staging Imports, Users & Roles, CODEX Hardware Workbench, Split-Pane Firmware Editor, and Audit/Health explorer)
Read-Only Viewer Account
Username / User ID: test_viewer
Password: TestViewerPass123!
Role: viewer

To RUN:
./run_clps.sh

To RUN on a different backend port:
./run_clps.sh start --backend-port=8005

To STOP
./run_clps.sh stop