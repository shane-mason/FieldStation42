import sqlite3

def delete_sequence_tables():
    db_path = "runtime/fs42.db"  # Adjust the path as necessary
    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS sequence_entries")
        cursor.execute("DROP TABLE IF EXISTS named_sequence")
        connection.commit()
        print("Deleted tables: sequence_entries, named_sequence")

if __name__ == "__main__":
    delete_sequence_tables()
