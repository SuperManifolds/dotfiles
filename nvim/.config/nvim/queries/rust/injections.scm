; extends
((macro_invocation
  (scoped_identifier
    path: (identifier) @_path
    name: (identifier) @_name)
  (token_tree
    . (raw_string_literal) @sql)
 (#eq? @_name "query")
 (#eq? @_path "sqlx"))
 (#offset! @sql 0 3 0 -2))

((macro_invocation
  (scoped_identifier
    path: (identifier) @_path
    name: (identifier) @_name)
  (token_tree
    . (string_literal) @sql)
 (#eq? @_name "query")
 (#eq? @_path "sqlx"))
 (#offset! @sql 0 1 0 -1))
