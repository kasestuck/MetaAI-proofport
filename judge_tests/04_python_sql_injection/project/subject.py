def build_query(identifier):
    return "SELECT name FROM items WHERE id = '%s'" % identifier
