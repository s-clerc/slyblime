def get_if_in(dictionary, *items):
    return tuple(dictionary[item] if item in dictionary else None 
                                  for item in items)



