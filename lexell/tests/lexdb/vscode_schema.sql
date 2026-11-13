-- The schema the VS Code replay (gen_vscode.py, run/tds_vscode.lxl) runs against, the same T-SQL on
-- SQL Server and on lexdb: customers and orders with a primary key, a foreign key, a unique and a check
-- constraint, defaults, an identity column, an index with INCLUDE, and a view. Batches end at GO.
IF OBJECT_ID('dbo.big_orders') IS NOT NULL DROP VIEW dbo.big_orders;
IF OBJECT_ID('dbo.orders') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.customers') IS NOT NULL DROP TABLE dbo.customers;
GO
CREATE TABLE dbo.customers (id int IDENTITY(1,1) PRIMARY KEY, name nvarchar(100) NOT NULL, email varchar(200) NULL UNIQUE, created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME());
CREATE TABLE dbo.orders (id bigint PRIMARY KEY, customer_id int NOT NULL REFERENCES dbo.customers(id), amount decimal(10,2) NOT NULL CHECK (amount >= 0), placed date NOT NULL, note nvarchar(max) NULL, ref uniqueidentifier NULL, paid bit NOT NULL DEFAULT 0);
CREATE INDEX ix_orders_placed ON dbo.orders(placed) INCLUDE (amount);
GO
CREATE VIEW dbo.big_orders AS SELECT id, customer_id, amount FROM dbo.orders WHERE amount > 100;
GO
INSERT dbo.customers(name, email) VALUES (N'Ann', 'ann@example.com'), (N'Bob', NULL);
INSERT dbo.orders VALUES (1, 1, 150.00, '2024-05-01', NULL, NEWID(), 1), (2, 2, 20.50, '2024-05-02', N'gift', NULL, 0);
GO
