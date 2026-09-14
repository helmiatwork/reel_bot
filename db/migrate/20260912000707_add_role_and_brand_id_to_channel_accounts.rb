class AddRoleAndBrandIdToChannelAccounts < ActiveRecord::Migration[8.1]
  def change
    add_column :channel_accounts, :role, :string, default: "main", null: false
    add_column :channel_accounts, :brand_id, :integer
    add_index :channel_accounts, :role
    add_index :channel_accounts, :brand_id
  end
end
