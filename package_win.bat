pyinstaller -F --paths $env:CONDA_PREFIX --add-data "static;static" --add-data "%CONDA_PREFIX%/Lib/site-packages/xmlschema/schemas;xmlschema/schemas" --add-data "server;server"  --add-data "templates;templates" --hidden-import "scipy.spatial.transform._rotation_groups" --name cycif_viewer app.py
