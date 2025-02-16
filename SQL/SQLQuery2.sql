-- Table to store file history
CREATE TABLE FileHistory (
    id INT PRIMARY KEY IDENTITY(1,1),
    username NVARCHAR(50) NOT NULL,
    filename NVARCHAR(255) NOT NULL,
    filepath NVARCHAR(255) NOT NULL,
    operation NVARCHAR(50) NOT NULL, -- e.g., "upload", "translate", "compress", "merge"
    timestamp DATETIME DEFAULT GETDATE()
);

-- Table to store file organization (folders/categories)
CREATE TABLE FileOrganization (
    id INT PRIMARY KEY IDENTITY(1,1),
    username NVARCHAR(50) NOT NULL,
    foldername NVARCHAR(255) NOT NULL,
    filepath NVARCHAR(255) NOT NULL
);
