require("alex")
vim.cmd [[colorscheme tokyonight]]

vim.opt.title = true
vim.opt.titlestring = "nvim " .. vim.fn.fnamemodify(vim.fn.getcwd(), ":t")
