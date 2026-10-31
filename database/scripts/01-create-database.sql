/* Run against the SQL Server instance as an administrator after starting it. */
IF DB_ID(N'LedgerPilot') IS NULL
BEGIN
    CREATE DATABASE [LedgerPilot];
END;
GO
