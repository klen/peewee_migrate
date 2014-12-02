def migrate(migrator, database):
    migrator.rename_column('tag', 'created_at', 'updated_at')
